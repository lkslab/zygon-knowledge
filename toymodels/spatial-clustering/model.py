# SPDX-License-Identifier: MIT
"""spatial-clustering: what a network loses when its buses are merged.

Six buses in two meshed regions, a windy west and a load-heavy east, joined by two
tie lines. The full network is solved with Kirchhoff's laws over one week, then
clustered to two buses (one per region) with `n.cluster.spatial.cluster_by_busmap`
and solved again. Internal congestion and the nodal price spread inside each region
vanish; the tie-line capacity is summed. The comparison shows what a clustered model
can and cannot say about prices, flows and cost.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "spatial-clustering"
TITLE = "Spatial clustering of a six-bus network"

REGION = {"W1": "west", "W2": "west", "W3": "west", "E1": "east", "E2": "east", "E3": "east"}
COORDS = {"W1": (0, 0), "W2": (0, 1), "W3": (1, 0.5), "E1": (3, 0.5), "E2": (4, 0), "E3": (4, 1)}
GENS = {  # name: bus, carrier, p_nom, marginal cost
    "onwind W1": ("W1", "onwind", 800, 0.0),
    "onwind W2": ("W2", "onwind", 600, 0.0),
    "coal W3": ("W3", "coal", 300, 30.0),
    "CCGT E1": ("E1", "CCGT", 600, 60.0),
    "CCGT E2": ("E2", "CCGT", 400, 60.0),
    "OCGT E3": ("E3", "OCGT", 400, 120.0),
}
LOADS = {"W1": 100, "W2": 100, "W3": 150, "E1": 300, "E2": 300, "E3": 250}
LINES = {  # name: bus0, bus1, s_nom
    "W1-W2": ("W1", "W2", 300), "W2-W3": ("W2", "W3", 300), "W1-W3": ("W1", "W3", 300),
    "E1-E2": ("E1", "E2", 500), "E2-E3": ("E2", "E3", 500), "E1-E3": ("E1", "E3", 500),
    "W3-E1": ("W3", "E1", 350), "W2-E3": ("W2", "E3", 250),
}
VOLL = 3000


def build() -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(7))
    n.add("Carrier", ["AC", "onwind", "coal", "CCGT", "OCGT", "load shedding"])
    for bus, (x, y) in COORDS.items():
        n.add("Bus", bus, v_nom=380, carrier="AC", x=x, y=y)
    shape = profiles.daily_load(n.snapshots, 0.7, 1.0, noise=0.0)
    wind = {"W1": profiles.wind(n.snapshots, mean_cf=0.45, seed=3), "W2": profiles.wind(n.snapshots, mean_cf=0.40, seed=5)}
    for name, (bus, carrier, p_nom, mc) in GENS.items():
        kw = {"p_max_pu": wind[bus]} if carrier == "onwind" else {}
        n.add("Generator", name, bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc, **kw)
    for bus, mw in LOADS.items():
        n.add("Load", f"load {bus}", bus=bus, carrier="load", p_set=shape * mw)
        n.add("Generator", f"shed {bus}", bus=bus, carrier="load shedding", p_nom=1e4, marginal_cost=VOLL)
    for name, (b0, b1, s_nom) in LINES.items():
        n.add("Line", name, bus0=b0, bus1=b1, x=0.1, r=0.01, s_nom=s_nom, carrier="AC")
    return n


def cluster(n: pypsa.Network) -> pypsa.Network:
    """Merge each region into one bus; parallel lines between regions are aggregated."""
    busmap = pd.Series(REGION, name="busmap")
    busmap.index.name = "Bus"
    return n.cluster.spatial.cluster_by_busmap(busmap.to_dict(), with_time=True)


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def runs() -> dict[str, pypsa.Network]:
    full = solve(build())
    clustered = solve(cluster(build()))
    return {"nodal": full, "clustered": clustered}


def _tie_flow(n: pypsa.Network) -> pd.Series:
    """West-to-east flow: on the full network the sum over the two tie lines."""
    if "W3-E1" in n.lines.index:
        return n.lines_t.p0["W3-E1"] + n.lines_t.p0["W2-E3"]
    line = n.lines.index[0]
    sign = 1 if n.lines.bus0[line] == "west" else -1
    return sign * n.lines_t.p0[line]


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    full, cl = nets["nodal"], nets["clustered"]
    lmp = full.buses_t.marginal_price
    spread_in = {r: float((lmp[[b for b, rr in REGION.items() if rr == r]].max(axis=1) - lmp[[b for b, rr in REGION.items() if rr == r]].min(axis=1)).mean()) for r in ("west", "east")}
    cl_price = cl.buses_t.marginal_price
    tie_full, tie_cl = _tie_flow(full), _tie_flow(cl)
    loading = (full.lines_t.p0.abs() / full.lines.s_nom)
    wind_avail = sum((full.generators_t.p_max_pu[g] * GENS[g][2]).sum() for g in ("onwind W1", "onwind W2"))
    return {
        "cost_eur": {"nodal": float(full.objective), "clustered": float(cl.objective)},
        "cost_difference_pct": float(100 * (cl.objective - full.objective) / full.objective),
        "buses_and_lines": {"nodal": [int(len(full.buses)), int(len(full.lines))], "clustered": [int(len(cl.buses)), int(len(cl.lines))]},
        "tie_capacity_mw": {"nodal": float(full.lines.s_nom[["W3-E1", "W2-E3"]].sum()), "clustered": float(cl.lines.s_nom.sum())},
        "mean_price_eur_mwh": {"nodal": {b: float(lmp[b].mean()) for b in REGION}, "clustered": {b: float(cl_price[b].mean()) for b in cl.buses.index}},
        "mean_intra_region_price_spread_eur_mwh": spread_in,
        "mean_west_east_spread_eur_mwh": {"nodal": float((lmp[["E1", "E2", "E3"]].mean(axis=1) - lmp[["W1", "W2", "W3"]].mean(axis=1)).mean()),
                                          "clustered": float((cl_price["east"] - cl_price["west"]).mean())},
        "tie_flow_mwh": {"nodal": float(tie_full.sum()), "clustered": float(tie_cl.sum())},
        "hours_any_internal_line_congested": int((loading[[l for l in LINES if l not in ("W3-E1", "W2-E3")]] > 0.999).any(axis=1).sum()),
        "wind_curtailed_pct": {"nodal": float(100 * (1 - (full.generators_t.p["onwind W1"] + full.generators_t.p["onwind W2"]).sum() / wind_avail)),
                               "clustered": float(100 * (1 - cl.generators_t.p[[g for g in cl.generators.index if g.startswith("onwind")]].sum().sum() / wind_avail))},
    }


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    full, cl = nets["nodal"], nets["clustered"]
    lmp = full.buses_t.marginal_price.mean()
    buses = list(REGION)
    option, ds = charts.bars(buses, {"nodal": [round(float(lmp[b]), 1) for b in buses],
                                     "clustered": [round(float(cl.buses_t.marginal_price[REGION[b]].mean()), 1) for b in buses]}, "EUR/MWh", category_name="bus")
    prices = bundle.Figure(option, ds, title="Mean price per bus, nodal vs clustered",
                           caption="Clustering gives every bus in a region the region's price; the spread inside the "
                           "west, where the wind buses are cheaper than the coal bus, is gone.")
    load_full = (full.lines_t.p0.abs() / full.lines.s_nom * 100).mean()
    tie_cl = (cl.lines_t.p0.abs() / cl.lines.s_nom * 100).mean()
    lines = list(LINES)
    option, ds = charts.bars(lines, {"nodal": [round(float(load_full[l]), 1) for l in lines],
                                     "clustered": [round(float(tie_cl.iloc[0]), 1) if l in ("W3-E1", "W2-E3") else 0.0 for l in lines]}, "% of rating", horizontal=True, category_name="line")
    loading = bundle.Figure(option, ds, title="Mean line loading, nodal vs clustered",
                            caption="Internal lines do not exist after clustering; the two tie lines become one with "
                            "their ratings summed, which lets the clustered model push more west-east flow than "
                            "Kirchhoff's law allows on the real pair.")
    df = pd.DataFrame({"nodal": _tie_flow(full), "clustered": _tie_flow(cl)}).round(1)
    option, ds = charts.time_series(df, "MW west to east", slider=False)
    tie = bundle.Figure(option, ds, title="West-to-east transfer over the week",
                        caption="The clustered network transfers more in windy hours because the aggregated tie "
                        "line ignores the loop-flow limit on the individual lines.")
    return {"prices_nodal_vs_clustered": prices, "line_loading": loading, "tie_flow": tie}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
