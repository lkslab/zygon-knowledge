# SPDX-License-Identifier: MIT
"""demand-elasticity: the merit-order day with a demand side that responds to price.

Three clearings of the same fleet and day: a fixed load, a demand made of bid blocks
(an inelastic core at the value of lost load plus tranches with falling willingness to
pay) and a linear demand curve approximated by five equal blocks. Elastic demand
shaves the peak, caps the price and makes welfare, not cost, the objective.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "demand-elasticity"
TITLE = "Price-responsive demand and market clearing"

FLEET = {"nuclear": (2000, 10), "lignite": (3000, 25), "CCGT": (4000, 55), "OCGT": (2000, 110), "oil": (1000, 180)}
BASE_MW, PEAK_MW = 5000, 10500
VOLL = 3000
# demand cases: list of (share of the hourly load, willingness to pay EUR/MWh)
CASES: dict[str, list[tuple[float, float]] | None] = {
    "fixed load": None,
    "bid blocks": [(0.6, VOLL), (0.1, 300), (0.1, 150), (0.1, 80), (0.1, 40)],
    "linear demand": [(0.6, VOLL)] + [(0.08, wtp) for wtp in (200, 160, 120, 80, 40)],
}


def build(*, blocks: list[tuple[float, float]] | None = None) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(1))
    n.add("Carrier", list(FLEET) + ["load shedding", "load", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, (p_nom, mc) in FLEET.items():
        n.add("Generator", carrier, bus="grid", carrier=carrier, p_nom=p_nom, marginal_cost=mc)
    load = profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW)
    if blocks is None:
        n.add("Generator", "load shedding", bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=VOLL)
        n.add("Load", "demand", bus="grid", carrier="load", p_set=load)
    else:
        # each block is a sink (sign -1) paid its willingness to pay: a negative marginal
        # cost, so the objective becomes cost minus utility and the solve maximises welfare
        for i, (share, wtp) in enumerate(blocks):
            n.add("Generator", f"demand block {i}", bus="grid", carrier="load", sign=-1, p_nom=PEAK_MW,
                  p_max_pu=load * share / PEAK_MW, marginal_cost=-wtp)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def cases() -> dict[str, pypsa.Network]:
    return {name: solve(build(blocks=blocks)) for name, blocks in CASES.items()}


def consumption(n: pypsa.Network) -> pd.Series:
    if "demand" in n.loads.index:
        return n.loads_t.p_set["demand"] - n.generators_t.p["load shedding"]
    cols = [g for g in n.generators.index if g.startswith("demand block")]
    return n.generators_t.p[cols].sum(axis=1)


def welfare(n: pypsa.Network) -> dict[str, float]:
    price = n.buses_t.marginal_price["grid"]
    gens = [g for g in FLEET]
    producer = float(sum(((price - n.generators.marginal_cost[g]) * n.generators_t.p[g]).sum() for g in gens))
    if "demand" in n.loads.index:
        served = consumption(n)
        consumer = float(((VOLL - price) * served).sum())
    else:
        cols = [g for g in n.generators.index if g.startswith("demand block")]
        consumer = float(sum(((-n.generators.marginal_cost[g] - price) * n.generators_t.p[g]).sum() for g in cols))
    return {"consumer surplus": consumer, "producer surplus": producer, "welfare": consumer + producer}


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    fixed = nets["fixed load"]
    peak = fixed.loads_t.p_set["demand"].idxmax()
    out: dict = {"peak_hour": str(peak)}
    for name, n in nets.items():
        price = n.buses_t.marginal_price["grid"]
        cons = consumption(n)
        w = welfare(n)
        out[name] = {
            "peak_price_eur_mwh": float(price[peak]),
            "avg_price_eur_mwh": float((price * cons).sum() / cons.sum()),
            "consumed_mwh": float(cons.sum()),
            "peak_consumption_mw": float(cons[peak]),
            "consumer_surplus_meur": w["consumer surplus"] / 1e6,
            "producer_surplus_meur": w["producer surplus"] / 1e6,
            "welfare_meur": w["welfare"] / 1e6,
            "dispatch_cost_eur": float(sum((n.generators.marginal_cost[g] * n.generators_t.p[g]).sum() for g in FLEET)),
        }
    out["peak_demand_reduction_pct"] = {name: float(100 * (1 - out[name]["peak_consumption_mw"] / out["fixed load"]["peak_consumption_mw"])) for name in nets}
    return out


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    fixed = nets["fixed load"]
    peak = fixed.loads_t.p_set["demand"].idxmax()
    load_peak = float(fixed.loads_t.p_set.loc[peak, "demand"])
    gens = fixed.generators.loc[list(FLEET)].sort_values("marginal_cost")
    x1 = gens.p_nom.cumsum()
    seg = [pd.DataFrame({"x0": x1 - gens.p_nom, "x1": x1, "y": gens.marginal_cost, "name": gens.index})]
    for name in ("bid blocks", "linear demand"):
        blocks = CASES[name]
        q0 = 0.0
        rows = []
        for share, wtp in blocks:
            q1 = q0 + share * load_peak
            rows.append({"x0": q0, "x1": q1, "y": min(wtp, 400), "name": name})
            q0 = q1
        seg.append(pd.DataFrame(rows))
    segments = pd.concat(seg, ignore_index=True)
    option, ds = charts.step_curve(segments, "MW at the peak hour", "EUR/MWh")
    option["yAxis"]["max"] = 400
    for s in option["series"]:
        if s["name"] in ("bid blocks", "linear demand"):
            s["areaStyle"] = {"opacity": 0.0}
            s["lineStyle"] = {**s.get("lineStyle", {}), "type": "dashed"}
    curves = bundle.Figure(option, ds, title="Supply and demand curves at the peak hour",
                           caption="The supply staircase against the two demand staircases (the inelastic core at the "
                           "value of lost load is clipped at 400). The price is where demand crosses supply; the "
                           "fixed load is a vertical line at the right edge of the core.")
    prices = pd.DataFrame({name: n.buses_t.marginal_price["grid"].round(2) for name, n in nets.items()})
    option, ds = charts.time_series(prices, "EUR/MWh", step="end")
    price_fig = bundle.Figure(option, ds, title="Hourly price by demand case",
                              caption="With elastic demand the evening peak no longer reaches the peaker: the last "
                              "tranche of demand drops out before the price climbs.")
    labels = list(nets)
    w = {name: welfare(n) for name, n in nets.items()}
    option, ds = charts.bars(labels, {"consumer surplus": [round(w[l]["consumer surplus"] / 1e6, 2) for l in labels],
                                      "producer surplus": [round(w[l]["producer surplus"] / 1e6, 2) for l in labels]},
                             "MEUR/day", stack=True, horizontal=False, category_name="case")
    welfare_fig = bundle.Figure(option, ds, title="Welfare by demand case",
                                caption="Consumer surplus is willingness to pay minus price over what is consumed, "
                                "producer surplus is price minus marginal cost over what is generated. The fixed "
                                "load values every MWh at the value of lost load, hence its large consumer surplus.")
    return {"supply_demand_curves": curves, "price_by_case": price_fig, "welfare_by_case": welfare_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = cases()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
