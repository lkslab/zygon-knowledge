# SPDX-License-Identifier: MIT
"""cost-sensitivity: how the optimal mix and the system cost move with technology costs.

The two-fortnight single-node expansion (wind, solar, gas, battery, 20 % cap), first
with each overnight cost moved 30 % up and down on its own (a tornado), then with 16
joint draws from a Latin hypercube over all four (a crude global sensitivity). Numpy
sampling only; the point is which cost the answer hangs on.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, names, profiles, run  # noqa: E402

SLUG = "cost-sensitivity"
TITLE = "Sensitivity of the optimal mix to technology costs"

BASE = run.load_model("capacity-expansion-single-node")
TECH = BASE.TECH
PARAMS = ["onwind", "solar", "CCGT", "battery"]
SWING = 0.30
DRAWS = 16
SEED = 7
CAP_FRACTION = 0.2
MEAN_LOAD_MW = 100


def _capex(tech: str, multiplier: float = 1.0) -> float:
    t = TECH[tech]
    return finance.capital_cost(t["overnight"] * multiplier, t["life"], fom_pct=t["fom"])


def build(*, multipliers: dict[str, float] | None = None, co2_cap_t: float | None = None) -> pypsa.Network:
    mult = {p: 1.0 for p in PARAMS} | (multipliers or {})
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "load shedding", "onwind", "solar", "battery"])
    n.add("Carrier", "CCGT", co2_emissions=BASE.CO2_CCGT)
    n.add("Bus", "electricity", carrier="AC")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, MEAN_LOAD_MW).loc[index])
    n.add("Generator", names.gen("onwind"), bus="electricity", carrier="onwind", p_nom_extendable=True, capital_cost=_capex("onwind", mult["onwind"]),
          p_max_pu=profiles.wind(year).loc[index])
    n.add("Generator", names.gen("solar"), bus="electricity", carrier="solar", p_nom_extendable=True, capital_cost=_capex("solar", mult["solar"]),
          p_max_pu=profiles.solar(year).loc[index])
    n.add("Generator", names.gen("CCGT"), bus="electricity", carrier="CCGT", p_nom_extendable=True, capital_cost=_capex("CCGT", mult["CCGT"]),
          marginal_cost=TECH["CCGT"]["marginal_cost"])
    n.add("Generator", names.gen("load shedding"), bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    b = TECH["battery"]
    n.add("StorageUnit", names.unit("battery"), bus="electricity", carrier="battery", p_nom_extendable=True, capital_cost=_capex("battery", mult["battery"]),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
    if co2_cap_t is not None:
        n.add("GlobalConstraint", "co2_limit", type="primary_energy", carrier_attribute="co2_emissions", sense="<=", constant=co2_cap_t)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def capacities(n: pypsa.Network) -> dict[str, float]:
    return {"onwind": float(n.generators.p_nom_opt[names.gen("onwind")]), "solar": float(n.generators.p_nom_opt[names.gen("solar")]),
            "CCGT": float(n.generators.p_nom_opt[names.gen("CCGT")]), "battery": float(n.storage_units.p_nom_opt[names.unit("battery")])}


def reference_cap() -> float:
    ref = solve(build())
    return CAP_FRACTION * BASE.emissions_t(ref)


def tornado(cap: float) -> tuple[pd.DataFrame, dict]:
    base = solve(build(co2_cap_t=cap))
    base_cost = float(base.objective)
    rows = []
    for p in PARAMS:
        for label, mult in (("-30 %", 1 - SWING), ("+30 %", 1 + SWING)):
            n = solve(build(multipliers={p: mult}, co2_cap_t=cap))
            rows.append({"parameter": p, "case": label, "cost": float(n.objective), **capacities(n)})
    return pd.DataFrame(rows), {"cost": base_cost, **capacities(base)}


def latin_hypercube(draws: int, dims: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    u = (rng.permuted(np.tile(np.arange(draws), (dims, 1)), axis=1).T + rng.random((draws, dims))) / draws
    return 1 - SWING + 2 * SWING * u  # multipliers in [0.7, 1.3]


def sample(cap: float) -> pd.DataFrame:
    X = latin_hypercube(DRAWS, len(PARAMS), SEED)
    rows = []
    for x in X:
        mult = dict(zip(PARAMS, x))
        n = solve(build(multipliers=mult, co2_cap_t=cap))
        rows.append({**{f"m_{p}": float(v) for p, v in mult.items()}, "cost": float(n.objective), **capacities(n)})
    return pd.DataFrame(rows)


def numbers(tor: pd.DataFrame, base: dict, smp: pd.DataFrame) -> dict:
    elasticity = {}
    for p in PARAMS:
        lo = tor[(tor.parameter == p) & (tor.case == "-30 %")].cost.iloc[0]
        hi = tor[(tor.parameter == p) & (tor.case == "+30 %")].cost.iloc[0]
        elasticity[p] = float(((hi - lo) / base["cost"]) / (2 * SWING))
    X = smp[[f"m_{p}" for p in PARAMS]].to_numpy()
    y = smp["cost"].to_numpy()
    A = np.column_stack([np.ones(len(y)), X])
    beta = np.linalg.lstsq(A, y, rcond=None)[0][1:]
    explained = {p: float(beta[i] ** 2 * X[:, i].var()) for i, p in enumerate(PARAMS)}
    total = sum(explained.values())
    return {
        "base_cost_meur_a": base["cost"] / 1e6,
        "base_capacity_mw": {p: base[p] for p in PARAMS},
        "cost_elasticity": elasticity,
        "dominant_parameter": max(elasticity, key=lambda p: abs(elasticity[p])),
        "tornado_cost_meur_a": {p: {c: float(tor[(tor.parameter == p) & (tor.case == c)].cost.iloc[0] / 1e6) for c in ("-30 %", "+30 %")} for p in PARAMS},
        "capacity_range_across_draws_mw": {p: {"min": float(smp[p].min()), "median": float(smp[p].median()), "max": float(smp[p].max())} for p in PARAMS},
        "cost_range_across_draws_meur_a": {"min": float(smp.cost.min() / 1e6), "max": float(smp.cost.max() / 1e6)},
        "variance_share_linear_fit": {p: float(explained[p] / total) if total > 0 else None for p in PARAMS},
        "draws": DRAWS,
        "swing": SWING,
    }


def figures(tor: pd.DataFrame, base: dict, smp: pd.DataFrame) -> dict[str, bundle.Figure]:
    order = sorted(PARAMS, key=lambda p: -abs(tor[tor.parameter == p].cost.max() - tor[tor.parameter == p].cost.min()))
    delta = {c: [round(float(tor[(tor.parameter == p) & (tor.case == c)].cost.iloc[0] - base["cost"]) / 1e6, 3) for p in order] for c in ("-30 %", "+30 %")}
    option, ds = charts.bars([f"{p} overnight cost" for p in order], delta, "MEUR/a change in system cost", horizontal=True, category_name="parameter")
    tor_fig = bundle.Figure(option, ds, title="Tornado: system cost against each cost moved 30 %",
                            caption="Change in annual system cost when one overnight cost moves alone. The longest bar "
                            "is the number worth pinning down first.")
    stats = {s: [round(float(getattr(smp[p], s)()), 1) for p in PARAMS] for s in ("min", "median", "max")}
    option, ds = charts.bars(PARAMS, stats, "MW", horizontal=False, category_name="technology")
    rng_fig = bundle.Figure(option, ds, title="Capacity across 16 joint cost draws",
                            caption="Minimum, median and maximum optimal capacity over Latin-hypercube draws of all "
                            "four costs within plus or minus 30 %. A wide bar means the technology's role is a "
                            "cost call, a narrow one means it is structural.")
    pts = smp.sort_values("m_onwind")
    datasets = {"draws": charts.dataset(["wind cost multiplier", "cost", "onwind"], pts[["m_onwind", "cost", "onwind"]].assign(cost=pts.cost / 1e6).round(3).to_numpy().tolist())}
    palette = charts.Palette()
    series = [{"type": "scatter", "name": "system cost", "datasetId": "draws", "encode": {"x": "wind cost multiplier", "y": "cost"},
               "symbolSize": 10, **palette.style("system cost", line=False)}]
    option = {
        "dataset": [{"id": "draws"}],
        "tooltip": {"trigger": "item"},
        "grid": {**charts.GRID, "left": charts.AXIS_NAME_MARGIN, "bottom": 24},
        "xAxis": charts.x_value_axis("Wind overnight cost multiplier", min=0.7, max=1.3),
        "yAxis": charts.value_axis("MEUR/a"),
        "series": series,
    }
    sc_fig = bundle.Figure(option, datasets, title="System cost against the wind cost draw",
                           caption="Each point is one joint draw; the scatter around the trend is what the other three "
                           "costs contribute.")
    return {"tornado": tor_fig, "capacity_ranges": rng_fig, "cost_vs_wind_capex": sc_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    cap = reference_cap()
    tor, base = tornado(cap)
    smp = sample(cap)
    nums = numbers(tor, base, smp)
    figs = figures(tor, base, smp)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
