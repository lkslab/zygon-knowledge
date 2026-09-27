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
from _lib import bundle, charts, geography, profiles, run  # noqa: E402

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

# the six buses as a made-up country, wide from west to east: the windy west (W1 south-west,
# W2 north-west, W3 the coal district by the border), the load-heavy east
OUTLINE = [(0.8, 7.6), (2.4, 8.5), (4.3, 8.0), (6.2, 8.7), (8.1, 8.1), (10.0, 8.8), (12.0, 8.2), (13.9, 8.7),
           (15.3, 7.8), (15.0, 6.1), (15.6, 4.4), (15.1, 2.6), (15.4, 1.3), (13.8, 0.4), (11.8, 0.9), (9.9, 0.3),
           (8.0, 0.8), (6.1, 0.2), (4.2, 0.8), (2.3, 0.3), (0.9, 1.2), (0.5, 2.9), (1.0, 4.5), (0.4, 6.1)]
DIVIDE = [(8.1, 10), (7.7, 6.8), (8.3, 4.4), (7.8, 2.2), (8.2, -1)]  # west | east, the cluster boundary
CUTS_WEST = [[(4.4, 10), (4.0, 6.5), (4.5, 4.0), (4.1, -1)], [(-1, 4.8), (1.8, 4.3), (4.35, 4.9)]]
CUTS_EAST = [[(11.8, 10), (12.2, 6.5), (11.7, 4.0), (12.1, -1)], [(11.85, 4.4), (14.0, 5.0), (17, 4.5)]]
BUS_XY = {"W1": (2.4, 2.6), "W2": (2.4, 6.5), "W3": (6.2, 4.4), "E1": (10.0, 4.4), "E2": (13.6, 2.6), "E3": (13.6, 6.5)}
KIND = {"W1": "windy coast", "W2": "windy hills", "W3": "coal district", "E1": "industry", "E2": "city", "E3": "city"}
BUS_LABEL_AT = {"W1": (2.4, 1.2), "W2": (2.4, 7.6), "W3": (6.2, 1.6), "E1": (10.0, 1.6), "E2": (13.6, 1.2), "E3": (13.6, 7.6)}
SITE_LABEL = {"W1": "left", "W2": "left", "W3": "bottom", "E1": "bottom", "E2": "right", "E3": "right"}
CLUSTER_XY = {"west": (4.4, 4.4), "east": (11.8, 4.4)}
CLUSTER_LABEL_AT = {"west": (4.4, 7.2), "east": (11.8, 7.2)}
TIE_LABEL_AT = {"W3-E1": (8.0, 3.6), "W2-E3": (8.0, 7.35)}


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


def _country() -> tuple[list, dict, dict, list]:
    outline, _ = geography.country(OUTLINE, [DIVIDE], CLUSTER_XY)
    _, clusters = geography.country(OUTLINE, [DIVIDE], CLUSTER_XY)
    _, buses = geography.country(OUTLINE, [DIVIDE, *CUTS_WEST, *CUTS_EAST], BUS_XY)
    return outline, buses, clusters, geography.inside(outline, DIVIDE)


def _net(n: pypsa.Network) -> pd.Series:
    """Mean net position per bus (generation minus load), MW."""
    gen = n.generators_t.p.T.groupby(n.generators.bus).sum().T.mean()
    load = n.loads_t.p_set.T.groupby(n.loads.bus).sum().T.mean()
    return gen.sub(load, fill_value=0.0)


def _reach(nets: dict[str, pypsa.Network]) -> float:
    return max(float(_net(n).abs().max()) for n in nets.values()) / 1e3


def network_before_clustering(nets: dict[str, pypsa.Network]) -> bundle.Figure:
    """The six-bus country: the price differs from bus to bus even inside a region."""
    full = nets["nodal"]
    outline, buses, _, divide = _country()
    net = _net(full)
    lmp = full.buses_t.marginal_price.mean()
    regions = [charts.Region(b, buses[b], value=round(float(net[b]) / 1e3, 3), label_at=BUS_LABEL_AT[b],
                             label=f"{KIND[b]} · price {lmp[b]:.0f}") for b in REGION]
    sites = [charts.Site(g, *BUS_XY[bus], size=p_nom, carrier=carrier, label=f"{carrier} {p_nom} MW",
                         label_position=SITE_LABEL[bus])
             for g, (bus, carrier, p_nom, _) in GENS.items()]
    flows = full.lines_t.p0.mean()
    links = [charts.Link(name, BUS_XY[b0], BUS_XY[b1], capacity=s_nom, flow=round(float(flows[name]), 1),
                         label=f"tie line {s_nom} MW" if name in TIE_LABEL_AT else None, label_at=TIE_LABEL_AT.get(name))
             for name, (b0, b1, s_nom) in LINES.items()]
    option, ds = charts.region_map(regions, outline=outline, sites=sites, links=links, borders=[divide],
                                   value_name="mean net position", unit="GW", low_label="short of power",
                                   high_label="power to spare", reach=_reach(nets), height=480,
                                   map_name="six buses")
    return bundle.Figure(
        option, ds, title="Six buses: a price for every place",
        caption="The full network as a made-up country: a windy west and a load-heavy east, the dark line between them "
        "the boundary the clustering will merge along. Prices (EUR/MWh, the week's mean) differ inside each half, "
        "because its own lines limit what can move, and the two tie lines limit what crosses.",
    )


def network_after_clustering(nets: dict[str, pypsa.Network]) -> bundle.Figure:
    """The same country clustered to two buses: one price per half, one summed tie line."""
    full, cl = nets["nodal"], nets["clustered"]
    outline, _, clusters, _ = _country()
    net = _net(cl)
    lmp = cl.buses_t.marginal_price.mean()
    regions = []
    for r in ("west", "east"):
        members = [b for b, rr in REGION.items() if rr == r]
        spread = f"{min(full.buses_t.marginal_price.mean()[members]):.0f} to {max(full.buses_t.marginal_price.mean()[members]):.0f}"
        regions.append(charts.Region(r.capitalize(), clusters[r], value=round(float(net[r]) / 1e3, 3),
                                     label_at=CLUSTER_LABEL_AT[r],
                                     label=f"one bus, one price: {lmp[r]:.0f} EUR/MWh\n(nodal: {spread})"))
    sites = []
    for r, (x, y) in CLUSTER_XY.items():
        here = [(g, c, p_nom) for g, (bus, c, p_nom, _) in GENS.items() if REGION[bus] == r]
        by_carrier: dict[str, float] = {}
        for _, c, p_nom in here:
            by_carrier[c] = by_carrier.get(c, 0.0) + p_nom
        for k, (c, p_nom) in enumerate(by_carrier.items()):
            dx = (k - (len(by_carrier) - 1) / 2) * 2.4
            sites.append(charts.Site(f"{c} {r}", x + dx, y - 1.6, size=p_nom, carrier=c, label=f"{c} {p_nom:.0f} MW",
                                     label_position="bottom"))
    line = cl.lines.index[0]
    s_nom = float(cl.lines.s_nom[line])
    sign = 1 if cl.lines.bus0[line] == "west" else -1
    flow = sign * float(cl.lines_t.p0[line].mean())
    tie = charts.Link("tie", CLUSTER_XY["west"], CLUSTER_XY["east"], capacity=s_nom, flow=round(flow, 1),
                      label=f"one tie line: {s_nom:.0f} MW\n(350 + 250 summed)", label_at=(8.0, 5.3))
    option, ds = charts.region_map(regions, outline=outline, sites=sites, links=[tie],
                                   value_name="mean net position", unit="GW", low_label="short of power",
                                   high_label="power to spare", reach=_reach(nets), height=480,
                                   map_name="two buses")
    return bundle.Figure(
        option, ds, title="Two buses: the detail inside each half is gone",
        caption="The same country clustered to one bus per half. Each half gets one price, the lines inside it vanish, "
        "and the two tie lines become one with their ratings summed, so the clustered model moves more power "
        "west to east than the real pair of lines allows, and finds a cheaper week than the full network does.",
    )


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
    return {"network_before_clustering": network_before_clustering(nets), "network_after_clustering": network_after_clustering(nets), "prices_nodal_vs_clustered": prices, "line_loading": loading, "tie_flow": tie}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
