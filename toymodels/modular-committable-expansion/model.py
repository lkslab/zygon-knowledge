# SPDX-License-Identifier: MIT
"""modular-committable-expansion: what changes when gas can only be built in 100 MW
blocks and has to be committed with start-up costs.

The two-fortnight single node with wind, solar, a battery and gas. Once: continuous
capacities, no commitment (the linear relaxation). Then: gas capacity in whole blocks
(`p_nom_mod`) and committable with a minimum part load and start-up costs, a mixed-
integer problem. The lumpy plan costs noticeably more, and the zero-profit identity that
holds for the LP breaks: with duals taken from a fixed-commitment re-solve, gas either
over- or under-recovers its cost.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, profiles, run  # noqa: E402

SLUG = "modular-committable-expansion"
TITLE = "Modular and committable expansion"

BASE = run.load_model("capacity-expansion-single-node")
TECH = BASE.TECH
MEAN_LOAD_MW = 100
CAP_FRACTION = 0.3
BLOCK_MW = 100
GAS_UC = dict(p_min_pu=0.4, start_up_cost=20_000, min_up_time=2, min_down_time=2)
CARRIERS = ["onwind", "solar", "CCGT", "battery"]


def _capex(tech: str) -> float:
    t = TECH[tech]
    return finance.capital_cost(t["overnight"], t["life"], fom_pct=t["fom"])


def build(*, modular: bool = True, co2_cap_t: float | None = None) -> pypsa.Network:
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "load shedding", "onwind", "solar", "battery"])
    n.add("Carrier", "CCGT", co2_emissions=BASE.CO2_CCGT)
    n.add("Bus", "electricity", carrier="AC")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, MEAN_LOAD_MW).loc[index])
    n.add("Generator", "onwind", bus="electricity", carrier="onwind", p_nom_extendable=True, capital_cost=_capex("onwind"),
          p_max_pu=profiles.wind(year).loc[index])
    n.add("Generator", "solar", bus="electricity", carrier="solar", p_nom_extendable=True, capital_cost=_capex("solar"),
          p_max_pu=profiles.solar(year).loc[index])
    gas = dict(bus="electricity", carrier="CCGT", p_nom_extendable=True, capital_cost=_capex("CCGT"),
               marginal_cost=TECH["CCGT"]["marginal_cost"])
    if modular:
        gas.update(p_nom_mod=BLOCK_MW, committable=True, **GAS_UC)
    n.add("Generator", "CCGT", **gas)
    n.add("Generator", "load shedding", bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    b = TECH["battery"]
    n.add("StorageUnit", "battery", bus="electricity", carrier="battery", p_nom_extendable=True, capital_cost=_capex("battery"),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
    if co2_cap_t is not None:
        n.add("GlobalConstraint", "co2_limit", type="primary_energy", carrier_attribute="co2_emissions", sense="<=", constant=co2_cap_t)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n, solver_options={"mip_rel_gap": 1e-4})


def capacities(n: pypsa.Network) -> pd.Series:
    return pd.Series({"onwind": n.generators.p_nom_opt["onwind"], "solar": n.generators.p_nom_opt["solar"],
                      "CCGT": n.generators.p_nom_opt["CCGT"], "battery": n.storage_units.p_nom_opt["battery"]})


def fixed_commitment_lp(n: pypsa.Network) -> pypsa.Network:
    """Freeze capacities and the MILP's commitment, solve the LP for prices."""
    m = build(modular=False, co2_cap_t=float(n.global_constraints.constant["co2_limit"]))
    cap = capacities(n)
    for g in ("onwind", "solar", "CCGT"):
        m.generators.loc[g, ["p_nom", "p_nom_extendable"]] = [cap[g], False]
    m.storage_units.loc["battery", ["p_nom", "p_nom_extendable"]] = [cap["battery"], False]
    status = n.generators_t.status["CCGT"].astype(float)
    m.generators_t.p_max_pu["CCGT"] = status
    m.generators_t.p_min_pu["CCGT"] = status * GAS_UC["p_min_pu"]
    run.solve(m)
    return m


def cost_recovery(n: pypsa.Network, prices: pypsa.Network) -> pd.DataFrame:
    w = n.snapshot_weightings.generators
    price = prices.buses_t.marginal_price["electricity"]
    cap = capacities(n)
    rows = {}
    co2 = float(-prices.global_constraints.mu["co2_limit"])
    for g in ("onwind", "solar", "CCGT"):
        p = n.generators_t.p[g]
        revenue = float((price * p * w).sum())
        mc = n.generators.marginal_cost[g] + (co2 * BASE.CO2_CCGT if g == "CCGT" else 0.0)
        cost = float(cap[g] * _capex(g) + (mc * p * w).sum())
        if g == "CCGT" and "status" in n.generators_t and "CCGT" in n.generators_t.status:
            starts = (n.generators_t.status["CCGT"].diff().fillna(0) > 0)
            cost += float((starts * GAS_UC["start_up_cost"] * w).sum())
        rows[g] = {"revenue": revenue, "cost": cost}
    return pd.DataFrame(rows).T


def runs() -> dict:
    ref = solve(build(modular=False))
    e0 = BASE.emissions_t(ref)
    cap = CAP_FRACTION * e0
    relaxed = solve(build(modular=False, co2_cap_t=cap))
    milp = solve(build(modular=True, co2_cap_t=cap))
    prices = fixed_commitment_lp(milp)
    return {"relaxed": relaxed, "milp": milp, "prices": prices}


def numbers(res: dict) -> dict:
    relaxed, milp, prices = res["relaxed"], res["milp"], res["prices"]
    cr_milp = cost_recovery(milp, prices)
    cr_lp = cost_recovery(relaxed, relaxed)
    status = milp.generators_t.status["CCGT"]
    starts = int((status.diff().fillna(0) > 0).sum())
    w = milp.snapshot_weightings.generators
    return {
        "cost_relaxed_meur_a": float(relaxed.objective / 1e6),
        "cost_milp_meur_a": float(milp.objective / 1e6),
        "integrality_gap_pct": float(100 * (milp.objective - relaxed.objective) / relaxed.objective),
        "capacity_mw": {"relaxed": {c: float(v) for c, v in capacities(relaxed).items()},
                        "modular": {c: float(v) for c, v in capacities(milp).items()}},
        "gas_blocks_built": int(round(capacities(milp)["CCGT"] / BLOCK_MW)),
        "gas_start_ups_in_two_fortnights": starts,
        "gas_hours_committed_pct": float(100 * (status * w).sum() / w.sum()),
        "cost_recovery_ratio": {"relaxed": {g: float(r.revenue / r.cost) for g, r in cr_lp.iterrows()},
                                "modular": {g: float(r.revenue / r.cost) if r.cost > 0 else None for g, r in cr_milp.iterrows()}},
        "gas_profit_meur_a": float((cr_milp.loc["CCGT", "revenue"] - cr_milp.loc["CCGT", "cost"]) / 1e6),
        "co2_price_eur_t": {"relaxed": float(-relaxed.global_constraints.mu["co2_limit"]), "fixed_commitment_lp": float(-prices.global_constraints.mu["co2_limit"])},
    }


def figures(res: dict) -> dict[str, bundle.Figure]:
    relaxed, milp, prices = res["relaxed"], res["milp"], res["prices"]
    option, ds = charts.bars(CARRIERS, {"continuous": [round(float(v), 1) for v in capacities(relaxed)],
                                        "modular + committable": [round(float(v), 1) for v in capacities(milp)]}, "MW", category_name="technology")
    cap = bundle.Figure(option, ds, title="Capacity: continuous relaxation vs blocks with commitment",
                        caption="Gas snaps to a whole number of 100 MW blocks; wind, solar and the battery move to fill "
                        "the gap the rounding leaves.")
    week = milp.snapshots[:56]
    stack = pd.DataFrame({c: milp.generators_t.p.loc[week, c] for c in ("onwind", "solar", "CCGT")})
    stack["battery"] = milp.storage_units_t.p.loc[week, "battery"].clip(lower=0)
    option, ds = charts.time_series(stack.round(1), "MW", stack=True, area=True, slider=False)
    disp = bundle.Figure(option, ds, title="Dispatch in the winter fortnight with commitment",
                         caption="Committed gas never runs below 40 % of its blocks; the start-up cost makes it stay on "
                         "through short dips rather than cycle.")
    cr_lp, cr_milp = cost_recovery(relaxed, relaxed) / 1e6, cost_recovery(milp, prices) / 1e6
    techs = ["onwind", "solar", "CCGT"]
    labels = [f"{t} {k}" for t in techs for k in ("LP", "MILP")]
    option, ds = charts.bars(labels, {"revenue": [round(float((cr_lp if k == "LP" else cr_milp).loc[t, "revenue"]), 3) for t in techs for k in ("LP", "MILP")],
                                      "cost": [round(float((cr_lp if k == "LP" else cr_milp).loc[t, "cost"]), 3) for t in techs for k in ("LP", "MILP")]},
                             "MEUR/a", category_name="technology and problem")
    rc = bundle.Figure(option, ds, title="Revenue against cost: the zero-profit identity breaks",
                       caption="In the LP every technology recovers its cost exactly. With blocks and commitment, "
                       "prices come from a fixed-commitment re-solve and gas no longer breaks even: lumpy "
                       "investment is why real markets need capacity mechanisms or make-whole payments.")
    return {"capacity_continuous_vs_modular": cap, "dispatch_with_commitment": disp, "cost_recovery_lp_vs_milp": rc}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    res = runs()
    nums = numbers(res)
    figs = figures(res)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
