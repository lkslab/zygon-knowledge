# SPDX-License-Identifier: MIT
"""nodal-prices-lopf: a three-bus meshed AC network with one congested line.

Linear optimal power flow: Kirchhoff's voltage law ties the flows on the three lines
of the triangle together, so when the cheap bus cannot export any more through the
small line, the price splits by bus. The load is scaled through six levels to show the
prices converge at low load and diverge once the line binds.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, geography, run  # noqa: E402

SLUG = "nodal-prices-lopf"
TITLE = "Nodal prices in a congested triangle"

BUSES = ["A", "B", "C"]
# generator per bus: (carrier, capacity MW, marginal cost EUR/MWh)
GENS = {"A": ("coal", 1000, 20), "B": ("CCGT", 1000, 60), "C": ("oil", 500, 120)}
LOADS = {"A": 100, "B": 600, "C": 400}  # MW at load level 1.0
LINES = {"A-B": ("A", "B", 400), "B-C": ("B", "C", 1000), "A-C": ("A", "C", 1000)}  # s_nom MW
X_PU = 0.1  # equal reactance on every line, so flows split by KVL alone
LOAD_LEVELS = [0.5, 0.7, 0.9, 1.0, 1.1, 1.2]

# the triangle as a made-up country: A the coal country in the north, B a city in the
# south-west, C a town in the south-east
OUTLINE = [(1.2, 10.6), (2.6, 11.8), (4.2, 11.3), (5.6, 12.1), (7.2, 11.4), (8.6, 11.7), (9.3, 10.2),
           (8.9, 8.6), (9.7, 7.1), (9.2, 5.4), (9.8, 3.8), (9.0, 2.2), (7.6, 0.9), (5.9, 0.6), (4.4, 1.0),
           (2.8, 0.4), (1.4, 1.2), (0.6, 2.9), (1.0, 4.6), (0.4, 6.2), (0.9, 7.8), (0.5, 9.3)]
CUTS = [[(-1, 6.4), (2, 6.9), (4, 6.2), (6, 6.8), (8, 6.3), (11, 6.7)],
        [(5.2, 7.4), (4.8, 5.0), (5.3, 3.0), (4.9, -1)]]
REGIONS = {  # bus: (region name, what it is, where its label sits)
    "A": ("A", "coal country", (5.0, 11.0)),
    "B": ("B", "city", (2.7, 1.9)),
    "C": ("C", "town", (7.4, 1.9)),
}
BUS_XY = {"A": (5.0, 8.9), "B": (2.7, 4.2), "C": (7.4, 4.2)}
LINK_LABEL_AT = {"A-B": (2.3, 7.7), "A-C": (7.7, 7.7), "B-C": (3.7, 3.55)}


def build(*, load_levels: list[float] | None = None, s_nom_ab: float = 400) -> pypsa.Network:
    levels = load_levels or LOAD_LEVELS
    n = pypsa.Network()
    n.set_snapshots(pd.Index([f"{int(round(100 * lv))}% load" for lv in levels], name="snapshot"))
    n.add("Carrier", ["AC", "coal", "CCGT", "oil", "load shedding"])
    n.add("Bus", BUSES, v_nom=380, carrier="AC")
    for bus, (carrier, p_nom, mc) in GENS.items():
        n.add("Generator", f"{carrier} {bus}", bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc)
        n.add("Generator", f"shed {bus}", bus=bus, carrier="load shedding", p_nom=1e4, marginal_cost=3000)
        n.add("Load", f"load {bus}", bus=bus, carrier="load", p_set=[LOADS[bus] * lv for lv in levels])
    for name, (b0, b1, s_nom) in LINES.items():
        n.add("Line", name, bus0=b0, bus1=b1, x=X_PU, r=0.01, s_nom=s_nom if name != "A-B" else s_nom_ab, carrier="AC")
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def _prices(n: pypsa.Network) -> pd.DataFrame:
    return n.buses_t.marginal_price[BUSES]


def _rent(n: pypsa.Network) -> pd.DataFrame:
    """Congestion rent per line and snapshot: |flow| times the price difference it bridges."""
    p0 = n.lines_t.p0
    lmp = _prices(n)
    rent = pd.DataFrame(index=n.snapshots, columns=list(LINES), dtype=float)
    for name, (b0, b1, _) in LINES.items():
        rent[name] = p0[name] * (lmp[b1] - lmp[b0])
    return rent


def numbers(n: pypsa.Network) -> dict:
    lmp = _prices(n)
    peak = n.snapshots[-1]
    rent = _rent(n)
    copper = build(s_nom_ab=1e5)
    solve(copper)
    loading = (n.lines_t.p0.abs() / n.lines.s_nom).loc[peak]
    return {
        "peak_prices_eur_mwh": {b: float(lmp.loc[peak, b]) for b in BUSES},
        "peak_price_spread_eur_mwh": float(lmp.loc[peak].max() - lmp.loc[peak].min()),
        "congestion_rent_peak_eur_h": float(rent.loc[peak].sum()),
        "congestion_rent_by_line_peak_eur_h": {k: float(v) for k, v in rent.loc[peak].items()},
        "line_loading_peak_pct": {k: float(100 * v) for k, v in loading.items()},
        "marginal_value_line_ab_peak_eur_mw_h": float(rent.loc[peak, "A-B"] / n.lines.s_nom["A-B"]),
        "cost_of_congestion_eur": float(n.objective - copper.objective),
        "first_congested_level": next((str(s) for s in n.snapshots if n.lines_t.p0.abs().loc[s, "A-B"] >= 0.999 * n.lines.s_nom["A-B"]), None),
        "loop_flow_share_peak": float(n.lines_t.p0.abs().loc[peak, "A-C"] / (n.lines_t.p0.abs().loc[peak, ["A-B", "A-C"]].sum())),
    }


def nodal_geography(n: pypsa.Network) -> bundle.Figure:
    """The triangle at peak load as a made-up country: cheap coal in the north, the demand in
    the south, the small line full, the rest of the coal taking the long way round."""
    peak = n.snapshots[-1]
    outline, rings = geography.country(OUTLINE, CUTS, BUS_XY)
    lmp = _prices(n).loc[peak]
    load = n.loads_t.p_set.loc[peak]
    made = n.generators_t.p.loc[peak].groupby(n.generators.bus).sum()
    regions, sites = [], []
    for bus, (name, kind, label_at) in REGIONS.items():
        use = float(load[f"load {bus}"])
        net = float(made.get(bus, 0.0)) - use
        regions.append(charts.Region(name=name, polygon=rings[bus], value=round(net / 1e3, 3), label_at=label_at,
                                     label=f"{kind}\nprice {lmp[bus]:.0f} EUR/MWh\nmakes {made.get(bus, 0.0):.0f} · uses {use:.0f} MW"))
        carrier, p_nom, mc = GENS[bus]
        sites.append(charts.Site(name=f"{carrier} {bus}", x=BUS_XY[bus][0], y=BUS_XY[bus][1], size=p_nom, carrier=carrier,
                                 label=f"{carrier}, {mc} EUR/MWh", label_position="right" if bus != "B" else "left"))
    flows = n.lines_t.p0.loc[peak]
    links = []
    for name, (b0, b1, _) in LINES.items():
        s_nom = float(n.lines.s_nom[name])
        f = float(flows[name])
        state = "full" if abs(f) >= 0.999 * s_nom else f"of {s_nom:,.0f}"
        links.append(charts.Link(name=name, start=BUS_XY[b0], end=BUS_XY[b1], capacity=s_nom, flow=round(f, 1),
                                 label=f"{name}: {abs(f):,.0f} MW {state}" if state == "full" else f"{name}: {abs(f):,.0f} {state} MW",
                                 label_at=LINK_LABEL_AT[name]))
    option, ds = charts.region_map(regions, outline=outline, sites=sites, links=links,
                                   value_name="net position", unit="GW", low_label="short of power",
                                   high_label="power to spare")
    return bundle.Figure(
        option, ds, title="Power takes every path: one full line splits the prices",
        caption="The three buses at peak load as a made-up country. Cheap coal in the north could serve the whole "
        "south, but the small A-B line is full. Power splits over every path, so more coal sent south, even towards "
        "C, would push part of it onto that line too; B and C must also run their dearer plants, and each bus gets "
        "its own price: cheap where power is stuck, dear where it is short.",
    )


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    lmp = _prices(n).round(2)
    levels = [str(s) for s in n.snapshots]
    option, ds = charts.bars(BUSES, {lv: lmp.loc[lv].tolist() for lv in levels}, "EUR/MWh", category_name="bus")
    prices = bundle.Figure(option, ds, title="Nodal prices by load level",
                           caption="One price while the network is unconstrained; once line A-B hits its limit the cheap "
                           "bus A decouples and B and C pay their own marginal units.")
    peak = n.snapshots[-1]
    flows = n.lines_t.p0.loc[peak].abs().round(1)
    option, ds = charts.bars(list(LINES), {"flow": flows.tolist(), "capacity": n.lines.s_nom.tolist()}, "MW",
                             horizontal=True, category_name="line")
    flow_fig = bundle.Figure(option, ds, title="Line flows at peak load", caption="Absolute flow against thermal limit; A-B is at its limit, the loop path A-C carries the rest.")
    rent = _rent(n).round(1)
    option, ds = charts.bars(list(LINES), {lv: rent.loc[lv].tolist() for lv in levels}, "EUR/h", category_name="line")
    rent_fig = bundle.Figure(option, ds, title="Congestion rent by line",
                             caption="Flow times the price difference across the line, the merchandising surplus a "
                             "transmission owner collects; zero until a constraint binds. B-C goes negative: "
                             "Kirchhoff's voltage law forces flow against the price gradient on the loop path.")
    return {"nodal_geography": nodal_geography(n), "nodal_prices": prices, "line_flows": flow_fig, "congestion_rent_by_line": rent_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
