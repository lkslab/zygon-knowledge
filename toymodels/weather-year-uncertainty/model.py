# SPDX-License-Identifier: MIT
"""weather-year-uncertainty: investment when the weather year itself is the unknown.

The two-fortnight single node with wind, solar, gas and a battery. Three weather
scenarios differ in their wind and solar time series (a calm, a normal and a windy
year), equally likely and unknown when capacities are chosen. Three deterministic
plans, the two-stage stochastic plan, and the normal-year plan evaluated across all
three years give the value of the stochastic solution and of perfect information,
this time for weather rather than a fuel price.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, names, profiles, run  # noqa: E402

SLUG = "weather-year-uncertainty"
TITLE = "Weather-year uncertainty in investment"

BASE = run.load_model("capacity-expansion-single-node")
TECH = BASE.TECH
MEAN_LOAD_MW = 100
CAP_FRACTION = 0.3
WEATHER = {"calm": dict(mean_cf=0.28, seed=11), "normal": dict(mean_cf=0.35, seed=42), "windy": dict(mean_cf=0.42, seed=7)}
PROB = {"calm": 1 / 3, "normal": 1 / 3, "windy": 1 / 3}
CARRIERS = ["onwind", "solar", "CCGT", "battery"]


def _capex(tech: str) -> float:
    t = TECH[tech]
    return finance.capital_cost(t["overnight"], t["life"], fom_pct=t["fom"])


def weather_series(name: str) -> tuple[pd.Series, pd.Series]:
    index, _ = profiles.representative_weeks()
    year = profiles.year_index()
    w = WEATHER[name]
    return profiles.wind(year, mean_cf=w["mean_cf"], seed=w["seed"]).loc[index], profiles.solar(year, seed=w["seed"]).loc[index]


def build(*, weather: str = "normal", scenarios: dict[str, float] | None = None, co2_cap_t: float | None = None,
          fixed: pd.Series | None = None) -> pypsa.Network:
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "load shedding", "onwind", "solar", "battery"])
    n.add("Carrier", "CCGT", co2_emissions=BASE.CO2_CCGT)
    n.add("Bus", "electricity", carrier="AC")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, MEAN_LOAD_MW).loc[index])
    wind, solar = weather_series(weather)
    ext = fixed is None
    n.add("Generator", names.gen("onwind"), bus="electricity", carrier="onwind", p_nom_extendable=ext, capital_cost=_capex("onwind"),
          p_max_pu=wind, p_nom=0 if ext else fixed["onwind"])
    n.add("Generator", names.gen("solar"), bus="electricity", carrier="solar", p_nom_extendable=ext, capital_cost=_capex("solar"),
          p_max_pu=solar, p_nom=0 if ext else fixed["solar"])
    n.add("Generator", names.gen("CCGT"), bus="electricity", carrier="CCGT", p_nom_extendable=ext, capital_cost=_capex("CCGT"),
          marginal_cost=TECH["CCGT"]["marginal_cost"], p_nom=0 if ext else fixed["CCGT"])
    n.add("Generator", names.gen("load shedding"), bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    b = TECH["battery"]
    n.add("StorageUnit", names.unit("battery"), bus="electricity", carrier="battery", p_nom_extendable=ext, capital_cost=_capex("battery"),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True,
          p_nom=0 if ext else fixed["battery"])
    if co2_cap_t is not None:
        n.add("GlobalConstraint", "co2_limit", type="primary_energy", carrier_attribute="co2_emissions", sense="<=", constant=co2_cap_t)
    if scenarios:
        n.set_scenarios(scenarios)
        # after set_scenarios the time-series columns are (scenario, name): assign each year's profiles
        for sc in scenarios:
            w_sc, s_sc = weather_series(sc)
            n.generators_t.p_max_pu[(sc, names.gen("onwind"))] = w_sc.to_numpy()
            n.generators_t.p_max_pu[(sc, names.gen("solar"))] = s_sc.to_numpy()
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def capacities(n: pypsa.Network) -> pd.Series:
    g, s = n.generators.p_nom_opt, n.storage_units.p_nom_opt
    if isinstance(g.index, pd.MultiIndex):
        first = g.index.get_level_values(0)[0]
        g, s = g.xs(first, level="scenario"), s.xs(first, level="scenario")
    return pd.Series({"onwind": g[names.gen("onwind")], "solar": g[names.gen("solar")], "CCGT": g[names.gen("CCGT")], "battery": s[names.unit("battery")]})


def realised(n: pypsa.Network) -> dict[str, dict[str, float]]:
    """Per scenario: total cost (shared capex plus that year's opex) and curtailment."""
    cap = capacities(n)
    capex = sum(cap[c] * _capex(c) for c in CARRIERS)
    w = n.snapshot_weightings.generators
    p = n.generators_t.p
    out = {}
    scen = p.columns.get_level_values(0).unique() if isinstance(p.columns, pd.MultiIndex) else [None]
    for sc in scen:
        col = (lambda g: (sc, names.gen(g))) if sc is not None else names.gen
        mc = n.generators.marginal_cost
        gas = float(mc[col("CCGT")]); shed = float(mc[col("load shedding")])
        opex = float((p[col("CCGT")] * gas * w).sum() + (p[col("load shedding")] * shed * w).sum())
        avail = float(((n.generators_t.p_max_pu[col("onwind")] * cap["onwind"] + n.generators_t.p_max_pu[col("solar")] * cap["solar"]) * w).sum())
        used = float(((p[col("onwind")] + p[col("solar")]) * w).sum())
        out[str(sc) if sc is not None else "realised"] = {"total": float(capex + opex), "curtailment_pct": float(100 * (1 - used / avail)) if avail > 0 else 0.0,
                                                          "load_shed_mwh": float((p[col("load shedding")] * w).sum())}
    return out


def evaluate_plan(cap: pd.Series, co2_cap_t: float) -> dict[str, dict[str, float]]:
    out = {}
    for sc in WEATHER:
        m = solve(build(weather=sc, fixed=cap, co2_cap_t=co2_cap_t))
        out[sc] = realised(m)["realised"]
    return out


def runs() -> dict:
    ref = solve(build(weather="normal"))
    cap_t = CAP_FRACTION * BASE.emissions_t(ref)
    nets = {f"deterministic {sc}": solve(build(weather=sc, co2_cap_t=cap_t)) for sc in WEATHER}
    nets["stochastic"] = solve(build(scenarios=PROB, co2_cap_t=cap_t))
    return {"nets": nets, "cap_t": cap_t}


def numbers(res: dict) -> dict:
    nets, cap_t = res["nets"], res["cap_t"]
    det = {sc: nets[f"deterministic {sc}"] for sc in WEATHER}
    sp = nets["stochastic"]
    ws = sum(PROB[s] * det[s].objective for s in WEATHER)
    normal_plan = evaluate_plan(capacities(det["normal"]), cap_t)
    eev = sum(PROB[s] * normal_plan[s]["total"] for s in WEATHER)
    rc = realised(sp)
    caps = {name: capacities(n) for name, n in nets.items()}
    return {
        "capacity_mw": {name: {c: float(v) for c, v in cap.items()} for name, cap in caps.items()},
        "capacity_range_over_deterministic_plans_mw": {c: [float(min(caps[f"deterministic {s}"][c] for s in WEATHER)), float(max(caps[f"deterministic {s}"][c] for s in WEATHER))] for c in CARRIERS},
        "expected_cost_meur_a": {"wait_and_see": ws / 1e6, "stochastic": float(sp.objective) / 1e6, "normal_plan_eev": eev / 1e6},
        "evpi_meur_a": (float(sp.objective) - ws) / 1e6,
        "vss_meur_a": (eev - float(sp.objective)) / 1e6,
        "cost_by_weather_meur_a": {"stochastic": {s: rc[s]["total"] / 1e6 for s in WEATHER}, "normal_plan": {s: normal_plan[s]["total"] / 1e6 for s in WEATHER}},
        "curtailment_pct": {"stochastic": {s: rc[s]["curtailment_pct"] for s in WEATHER}, "normal_plan": {s: normal_plan[s]["curtailment_pct"] for s in WEATHER}},
        "load_shed_mwh": {"stochastic": {s: rc[s]["load_shed_mwh"] for s in WEATHER}, "normal_plan": {s: normal_plan[s]["load_shed_mwh"] for s in WEATHER}},
        "wind_mean_cf": {s: WEATHER[s]["mean_cf"] for s in WEATHER},
    }


def figures(res: dict) -> dict[str, bundle.Figure]:
    nets, cap_t = res["nets"], res["cap_t"]
    labels = list(nets)
    caps = pd.DataFrame({name: capacities(n) for name, n in nets.items()}).round(1)
    option, ds = charts.bars(labels, {c: caps.loc[c].tolist() for c in CARRIERS}, "MW", stack=True, horizontal=False, category_name="plan")
    mix = bundle.Figure(option, ds, title="Capacity by planning strategy",
                        caption="A plan for a calm year buys gas and solar, a plan for a windy year buys wind; the "
                        "stochastic plan sits between and keeps a little more firm capacity than any single year asks for.")
    normal_plan = evaluate_plan(capacities(nets["deterministic normal"]), cap_t)
    rc = realised(nets["stochastic"])
    scen = list(WEATHER)
    option, ds = charts.bars(scen, {"normal-year plan": [round(normal_plan[s]["total"] / 1e6, 2) for s in scen],
                                    "stochastic plan": [round(rc[s]["total"] / 1e6, 2) for s in scen]}, "MEUR/a", category_name="weather year")
    cost = bundle.Figure(option, ds, title="Realised annual cost under each weather year",
                         caption="The normal-year plan pays for its optimism in the calm year, mostly through gas and "
                         "lost load; the stochastic plan gives up a little in the windy year for that.")
    option, ds = charts.bars(scen, {"normal-year plan": [round(normal_plan[s]["curtailment_pct"], 1) for s in scen],
                                    "stochastic plan": [round(rc[s]["curtailment_pct"], 1) for s in scen]}, "%", category_name="weather year")
    curt = bundle.Figure(option, ds, title="Wind and solar curtailment under each weather year",
                         caption="Curtailment is the flip side of security: the plan that is safe in the calm year "
                         "wastes more in the windy one.")
    return {"capacity_by_plan": mix, "cost_by_weather_year": cost, "curtailment_by_weather_year": curt}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    res = runs()
    nums = numbers(res)
    figs = figures(res)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
