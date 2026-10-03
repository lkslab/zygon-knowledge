# SPDX-License-Identifier: MIT
"""mga-near-optimal: how different can a system look while costing almost the same?

The two-fortnight single-node expansion (wind, solar, gas, battery, 20 % CO2 cap) is
solved to its optimum, then re-solved with the cost held within a slack of that optimum
while each technology's capacity is pushed to its minimum and its maximum:
modelling-to-generate-alternatives. The ranges show which capacities the cost
optimum really pins down and which are a coin toss.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, names, profiles, run  # noqa: E402

SLUG = "mga-near-optimal"
TITLE = "Near-optimal alternatives (MGA)"

BASE = run.load_model("capacity-expansion-single-node")
TECH = BASE.TECH
MEAN_LOAD_MW = 100
CAP_FRACTION = 0.2
SLACK = 0.05
SLACKS = [0.01, 0.02, 0.05, 0.10]
CARRIERS = ["onwind", "solar", "CCGT", "battery"]
COMPONENT = {"onwind": "Generator", "solar": "Generator", "CCGT": "Generator", "battery": "StorageUnit"}


def _capex(tech: str) -> float:
    t = TECH[tech]
    return finance.capital_cost(t["overnight"], t["life"], fom_pct=t["fom"])


def build(*, co2_cap_t: float | None = None) -> pypsa.Network:
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "load shedding", "onwind", "solar", "battery"])
    n.add("Carrier", "CCGT", co2_emissions=BASE.CO2_CCGT)
    n.add("Bus", "electricity", carrier="AC")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, MEAN_LOAD_MW).loc[index])
    n.add("Generator", names.gen("onwind"), bus="electricity", carrier="onwind", p_nom_extendable=True, capital_cost=_capex("onwind"),
          p_max_pu=profiles.wind(year).loc[index])
    n.add("Generator", names.gen("solar"), bus="electricity", carrier="solar", p_nom_extendable=True, capital_cost=_capex("solar"),
          p_max_pu=profiles.solar(year).loc[index])
    n.add("Generator", names.gen("CCGT"), bus="electricity", carrier="CCGT", p_nom_extendable=True, capital_cost=_capex("CCGT"),
          marginal_cost=TECH["CCGT"]["marginal_cost"])
    n.add("Generator", names.gen("load shedding"), bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    b = TECH["battery"]
    n.add("StorageUnit", names.unit("battery"), bus="electricity", carrier="battery", p_nom_extendable=True, capital_cost=_capex("battery"),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
    if co2_cap_t is not None:
        n.add("GlobalConstraint", "co2_limit", type="primary_energy", carrier_attribute="co2_emissions", sense="<=", constant=co2_cap_t)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def capacities(n: pypsa.Network) -> pd.Series:
    return pd.Series({"onwind": n.generators.p_nom_opt[names.gen("onwind")], "solar": n.generators.p_nom_opt[names.gen("solar")],
                      "CCGT": n.generators.p_nom_opt[names.gen("CCGT")], "battery": n.storage_units.p_nom_opt[names.unit("battery")]})


def system_cost(n: pypsa.Network) -> float:
    """Annualised capex plus opex from the solution, independent of which objective was solved."""
    w = n.snapshot_weightings.generators
    cap = capacities(n)
    capex = sum(cap[c] * _capex(c) for c in CARRIERS)
    opex = float((n.generators_t.p * n.generators.marginal_cost).mul(w, axis=0).sum().sum())
    return float(capex + opex)


def _weights(tech: str) -> dict:
    name = names.unit(tech) if COMPONENT[tech] == "StorageUnit" else names.gen(tech)
    return {COMPONENT[tech]: {"p_nom": {name: 1.0}}}


def mga(optimum: pypsa.Network, tech: str, sense: str, slack: float) -> pypsa.Network:
    """Push one technology's capacity to its `sense` extreme within `slack` of the optimum cost."""
    m = optimum.copy()
    m._objective = optimum.objective  # the copy needs the optimum's cost for the budget constraint
    run.quiet()
    status, cond = m.optimize.optimize_mga(weights=_weights(tech), sense=sense, slack=slack, solver_name=run.SOLVER,
                                           solver_options={**run.QUIET_SOLVER, "solver": "ipm"}, progress=False)
    if status != "ok":
        raise RuntimeError(f"MGA {tech} {sense} ended {status}/{cond}")
    return m


def runs() -> dict:
    ref = solve(build())
    e0 = BASE.emissions_t(ref)
    optimum = solve(build(co2_cap_t=CAP_FRACTION * e0))
    alternatives: dict[str, pypsa.Network] = {}
    for tech in CARRIERS:
        for sense in ("min", "max"):
            alternatives[f"{sense} {tech}"] = mga(optimum, tech, sense, SLACK)
    sweep = {}
    for slack in SLACKS:
        sweep[slack] = {sense: capacities(mga(optimum, "onwind", sense, slack))["onwind"] for sense in ("min", "max")}
    return {"optimum": optimum, "alternatives": alternatives, "sweep": sweep}


def numbers(res: dict) -> dict:
    opt = res["optimum"]
    cap_opt = capacities(opt)
    ranges = {}
    for tech in CARRIERS:
        lo = capacities(res["alternatives"][f"min {tech}"])[tech]
        hi = capacities(res["alternatives"][f"max {tech}"])[tech]
        ranges[tech] = {"min": float(lo), "optimum": float(cap_opt[tech]), "max": float(hi),
                        "range_over_optimum_pct": float(100 * (hi - lo) / cap_opt[tech]) if cap_opt[tech] > 1e-3 else None}
    return {
        "optimum_cost_meur_a": float(opt.objective / 1e6),
        "slack_pct": 100 * SLACK,
        "slack_cost_meur_a": float(SLACK * opt.objective / 1e6),
        "capacity_range_mw": ranges,
        "alternative_costs_meur_a": {k: system_cost(m) / 1e6 for k, m in res["alternatives"].items()},
        "wind_range_by_slack_mw": {f"{100 * s:g}%": {k: float(v) for k, v in r.items()} for s, r in res["sweep"].items()},
        "co2_price_eur_t": float(-opt.global_constraints.mu["co2_limit"]),
    }


def figures(res: dict) -> dict[str, bundle.Figure]:
    opt = res["optimum"]
    cap_opt = capacities(opt)
    lo = [round(float(capacities(res["alternatives"][f"min {t}"])[t]), 1) for t in CARRIERS]
    hi = [round(float(capacities(res["alternatives"][f"max {t}"])[t]), 1) for t in CARRIERS]
    option, ds = charts.bars(CARRIERS, {"minimum": lo, "optimum": [round(float(cap_opt[t]), 1) for t in CARRIERS], "maximum": hi},
                             "MW", category_name="technology")
    rng = bundle.Figure(option, ds, title=f"Capacity ranges within {100 * SLACK:g} % of the optimal cost",
                        caption="For each technology, the least and the most that can be built while total cost stays "
                        "within the slack. A wide bar means the optimum barely constrains that choice.")
    labels = ["optimum", *res["alternatives"]]
    mixes = {c: [round(float(cap_opt[c]), 1)] + [round(float(capacities(m)[c]), 1) for m in res["alternatives"].values()] for c in CARRIERS}
    option, ds = charts.bars(labels, mixes, "MW", stack=True, horizontal=True, category_name="alternative")
    alt = bundle.Figure(option, ds, title="The near-optimal mixes",
                        caption="Each row is one alternative: the mix that minimises or maximises one technology within "
                        "the slack. Wind and solar trade against each other; gas capacity hardly moves because "
                        "the cap and the dark weeks fix it.")
    sw = pd.DataFrame({"min wind": [res["sweep"][s]["min"] for s in SLACKS], "max wind": [res["sweep"][s]["max"] for s in SLACKS]},
                      index=pd.Index([100 * s for s in SLACKS], name="slack")).round(1)
    option, ds = charts.xy_lines(sw, "Cost slack (%)", "MW", symbols=True, x_extra={"min": 0})
    swf = bundle.Figure(option, ds, title="Wind capacity range against cost slack",
                        caption="The feasible wind range opens quickly: a percent of extra cost buys a lot of freedom "
                        "in the mix. That flatness of the cost surface is the point of MGA.")
    return {"capacity_ranges": rng, "alternative_mixes": alt, "range_vs_slack": swf}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    res = runs()
    nums = numbers(res)
    figs = figures(res)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
