# SPDX-License-Identifier: MIT
"""redispatch: a zonal market that ignores an internal bottleneck, then the grid
operator's redispatch to make the schedule feasible, compared with nodal pricing.

Four buses: a windy, cheap north and a load-heavy south joined by two small lines.
Three solves: (1) the nodal reference, (2) a copper-plate zonal market that clears
as if the lines were infinite, (3) redispatch: the market dispatch is frozen and
every unit gets an up-twin and a down-twin the operator can call at a cost, so the
flows fit the real grid. The gap between (2)+(3) and (1) is the price of pretending.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "redispatch"
TITLE = "Zonal market, redispatch and nodal pricing"

BUSES = ["N1", "N2", "S1", "S2"]
GENS = {  # name: (bus, carrier, p_nom MW, marginal cost)
    "onwind N1": ("N1", "onwind", 3000, 0),
    "coal N2": ("N2", "coal", 1000, 30),
    "CCGT S1": ("S1", "CCGT", 2000, 60),
    "OCGT S2": ("S2", "OCGT", 1500, 120),
}
LOADS = {"N1": 300, "N2": 300, "S1": 1500, "S2": 1500}  # MW, scaled by a daily shape
LINES = {"N1-N2": ("N1", "N2", 2000), "S1-S2": ("S1", "S2", 2000), "N1-S1": ("N1", "S1", 400), "N2-S2": ("N2", "S2", 400)}
X_PU = 0.1
REDISPATCH_PREMIUM = 10  # EUR/MWh paid on top of cost for ramping a unit up; down-ramps refund cost minus this
VOLL = 3000


def build(*, copper_plate: bool = False) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(1))
    n.add("Carrier", ["AC", "onwind", "coal", "CCGT", "OCGT", "load shedding"])
    n.add("Bus", BUSES, v_nom=380, carrier="AC")
    shape = profiles.daily_load(n.snapshots, 0.7, 1.0, noise=0.0)
    for name, (bus, carrier, p_nom, mc) in GENS.items():
        kw = {"p_max_pu": profiles.wind(n.snapshots, mean_cf=0.5)} if carrier == "onwind" else {}
        n.add("Generator", name, bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc, **kw)
    for bus, mw in LOADS.items():
        n.add("Load", f"load {bus}", bus=bus, carrier="load", p_set=shape * mw)
        n.add("Generator", f"shed {bus}", bus=bus, carrier="load shedding", p_nom=1e4, marginal_cost=VOLL)
    for name, (b0, b1, s_nom) in LINES.items():
        n.add("Line", name, bus0=b0, bus1=b1, x=X_PU, r=0.01, carrier="AC", s_nom=s_nom * (100 if copper_plate else 1))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def build_redispatch(market: pypsa.Network) -> pypsa.Network:
    """Freeze the market dispatch on the real grid and add ramp-up / ramp-down twins."""
    n = build()
    p_market = market.generators_t.p
    for name, (bus, carrier, p_nom, mc) in GENS.items():
        share = (p_market[name] / p_nom).clip(0, 1)
        n.generators_t.p_min_pu[name] = share
        n.generators_t.p_max_pu[name] = share
        # ramp up: remaining headroom at cost plus premium; wind headroom follows its availability
        avail = market.generators_t.p_max_pu[name] if name in market.generators_t.p_max_pu else pd.Series(1.0, index=n.snapshots)
        n.add("Generator", f"{name} up", bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc + REDISPATCH_PREMIUM,
              p_max_pu=(avail - share).clip(lower=0))
        # ramp down: negative generation up to the scheduled amount; cost times negative output refunds the
        # avoided cost minus the premium (curtailing zero-cost wind costs the premium, nothing is earned)
        n.add("Generator", f"{name} down", bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc - REDISPATCH_PREMIUM,
              p_min_pu=-share, p_max_pu=0)
    return n


def stages() -> dict[str, pypsa.Network]:
    nodal = solve(build())
    market = solve(build(copper_plate=True))
    redispatch = solve(build_redispatch(market))
    return {"nodal": nodal, "zonal market": market, "redispatch": redispatch}


def _cost(n: pypsa.Network) -> float:
    return float(n.objective)


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    nodal, market, rd = nets["nodal"], nets["zonal market"], nets["redispatch"]
    up = rd.generators_t.p[[c for c in rd.generators.index if c.endswith(" up")]]
    down = rd.generators_t.p[[c for c in rd.generators.index if c.endswith(" down")]]
    rd_cost = _cost(rd) - _cost(market)
    wind_avail = (market.generators_t.p_max_pu["onwind N1"] * GENS["onwind N1"][2]).sum()
    return {
        "cost_nodal_eur": _cost(nodal),
        "cost_zonal_market_eur": _cost(market),
        "cost_redispatch_eur": rd_cost,
        "cost_zonal_plus_redispatch_eur": _cost(rd),
        "efficiency_loss_pct": float(100 * (_cost(rd) - _cost(nodal)) / _cost(nodal)),
        "redispatch_up_mwh": float(up.sum().sum()),
        "redispatch_down_mwh": float(-down.sum().sum()),
        "redispatch_by_unit_mwh": {g: {"up": float(up[f"{g} up"].sum()), "down": float(-down[f"{g} down"].sum())} for g in GENS},
        "wind_curtailed_mwh": {"nodal": float(wind_avail - nodal.generators_t.p["onwind N1"].sum()),
                               "zonal market": float(wind_avail - market.generators_t.p["onwind N1"].sum()),
                               "after redispatch": float(wind_avail - (market.generators_t.p["onwind N1"] + rd.generators_t.p["onwind N1 down"]).sum())},
        "avg_price_eur_mwh": {"nodal": {b: float(nodal.buses_t.marginal_price[b].mean()) for b in BUSES},
                              "zonal market": float(market.buses_t.marginal_price[BUSES].mean().mean())},
        "max_line_loading_market_pct": float(100 * (market.lines_t.p0.abs() / (market.lines.s_nom / 100)).max().max()),
    }


CORRIDOR = ["N1-S1", "N2-S2"]

# The made-up country the four buses sit in (abstract coordinates, north up): a ragged
# outline with a windy coast along the top, cut into four subregions by a wavy
# east-west and a north-south border so neighbours share their edges exactly.
OUTLINE = [(1.0, 11.2), (2.2, 11.9), (3.1, 11.3), (4.3, 12.0), (5.2, 11.4), (6.4, 11.9), (7.6, 11.2),
           (8.7, 11.6), (9.4, 10.4), (9.0, 9.1), (9.6, 7.8), (9.2, 6.2), (9.8, 4.9), (9.1, 3.4), (9.4, 2.0),
           (8.2, 0.9), (6.6, 0.4), (5.1, 0.8), (3.6, 0.3), (2.2, 0.9), (1.1, 1.8), (0.6, 3.3), (1.0, 4.8),
           (0.4, 6.3), (0.9, 7.7), (0.3, 9.1), (0.7, 10.2)]
EAST_WEST = [(-1, 6.0), (2, 6.5), (4, 5.8), (6, 6.4), (8, 5.9), (11, 6.3)]
NORTH_SOUTH = [(5.2, 13), (4.8, 9), (5.3, 6.2), (4.9, 3), (5.2, -1)]
REGIONS = {  # bus: (subregion name, what it is, where its label sits)
    "N1": ("North-west", "windy coast", (2.6, 10.4)),
    "N2": ("North-east", "coal country", (7.4, 10.4)),
    "S1": ("South-west", "city", (2.6, 1.9)),
    "S2": ("South-east", "industry", (7.4, 1.9)),
}
BUS_XY = {"N1": (2.4, 8.2), "N2": (7.6, 8.2), "S1": (2.4, 4.0), "S2": (7.6, 4.0)}
LINK_LABEL_AT = {"N1-S1": (1.45, 7.0), "N2-S2": (8.55, 7.0)}  # outside the corridor, clear of the arrow
SHORT_NAME = {"onwind": "wind", "coal": "coal", "CCGT": "gas", "OCGT": "peak gas"}


def country() -> tuple[list[tuple[float, float]], dict[str, list[tuple[float, float]]]]:
    """The smoothed outline and each bus's subregion ring, split with shapely."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import split

    shape = Polygon(OUTLINE).buffer(0.35, join_style="round").buffer(-0.35, join_style="round").simplify(0.03)
    pieces = []
    for half in split(shape, LineString(EAST_WEST)).geoms:
        pieces += list(split(half, LineString(NORTH_SOUTH)).geoms)
    rings = {}
    for bus, (x, y) in BUS_XY.items():
        piece = next(g for g in pieces if g.contains(Polygon([(x - .01, y - .01), (x + .01, y - .01), (x + .01, y + .01)])))
        rings[bus] = [(round(px, 3), round(py, 3)) for px, py in piece.exterior.coords]
    return [(round(px, 3), round(py, 3)) for px, py in shape.exterior.coords], rings


def redispatch_geography(market: pypsa.Network) -> bundle.Figure:
    """The country: where power is made and used, the lines between, and what the market plans."""
    outline, rings = country()
    load = market.loads_t.p_set.mean()
    gen_bus = market.generators.bus
    dispatch = market.generators_t.p.T.groupby(gen_bus).sum().T.mean()
    regions, sites = [], []
    for bus, (name, kind, label_at) in REGIONS.items():
        gens = [(g, spec) for g, spec in GENS.items() if spec[0] == bus]
        made = " · ".join(f"{SHORT_NAME[c]} {p_nom / 1e3:g} GW" for _, (_, c, p_nom, _) in gens)
        net = (dispatch.get(bus, 0.0) - load[f"load {bus}"]) / 1e3
        regions.append(charts.Region(name=name, polygon=rings[bus], value=round(float(net), 2), label_at=label_at,
                                     label=f"{kind}\n{made} · demand {load[f'load {bus}'] / 1e3:.1f} GW"))
        for g, (_, carrier, p_nom, mc) in gens:
            sites.append(charts.Site(name=g, x=BUS_XY[bus][0], y=BUS_XY[bus][1], size=p_nom, carrier=carrier,
                                     label=f"{SHORT_NAME[carrier]}, {mc} EUR/MWh",
                                     label_position="top" if bus.startswith("N") else "bottom"))
    flows = market.lines_t.p0.mean()
    links = [charts.Link(name=ln, start=BUS_XY[b0], end=BUS_XY[b1], capacity=s_nom, flow=round(float(flows[ln]), 1),
                         label=f"{s_nom} MW line" if ln in CORRIDOR else None,
                         label_at=LINK_LABEL_AT.get(ln))
             for ln, (b0, b1, s_nom) in LINES.items()]
    transfer = float(market.lines_t.p0[CORRIDOR].sum(axis=1).mean())
    arrow = charts.Arrow(name="market plan", start=(5.0, 9.4), end=(5.0, 3.4), value=transfer, label_at=(6.35, 7.0),
                         label=f"market plan:\n{transfer / 1e3:.1f} GW south")
    option, ds = charts.region_map(regions, outline=outline, sites=sites, links=links, arrows=[arrow],
                                   value_name="net position", unit="GW", low_label="short of power",
                                   high_label="power to spare")
    return bundle.Figure(option, ds, title="Where power is made, where it is used, and the lines between",
                         caption="A made-up country. The windy, thinly populated north makes far more than it uses, "
                         "the south's cities and industry use far more than they make. The market plans to move "
                         "about 2 GW south, but only two 400 MW lines join the halves: they would run far over "
                         "their limit.")


def redispatch_intuition(market: pypsa.Network) -> bundle.Figure:
    """The market's planned north-to-south transfer against what the two corridor lines carry."""
    limit = float(sum(LINES[ln][2] for ln in CORRIDOR))
    transfer = pd.DataFrame({"transfer": market.lines_t.p0[CORRIDOR].sum(axis=1).round(1)})
    band = charts.Band(value="transfer", value_name="north to south, as the market plans it", level=limit,
                       level_name="what the two lines carry", below=None, under="carried by the two lines",
                       above="more than the lines carry: redispatched", unit="MW")
    option, ds = charts.fill_between(transfer, band)
    return bundle.Figure(option, ds, title="What redispatch fixes: the market's plan against the grid",
                         caption="The market clears as if the north-south lines were unlimited and plans to send "
                         "about 2 GW south all day. The green part the two lines carry; the orange band is what the "
                         "operator turns down in the north and up in the south, hour by hour.")


def price_by_bus(nodal: pypsa.Network, market: pypsa.Network) -> bundle.Figure:
    """Mean nodal price per bus against the single zonal price."""
    nodal_price = [round(float(nodal.buses_t.marginal_price[b].mean()), 1) for b in BUSES]
    zonal = round(float(market.buses_t.marginal_price[BUSES].mean().mean()), 1)
    option, ds = charts.bars(BUSES, {"nodal price": nodal_price}, "EUR/MWh", category_name="bus")
    # replaces the zero line bars() draws under a negative bar with a labelled pair
    marks = [{"value": 0}] if min(nodal_price) < 0 else []
    marks.append({"value": zonal, "label": f"one zonal price, {zonal:.0f}"})
    mark_line = charts.mark_lines(marks, axis="yAxis")
    mark_line["label"]["position"] = "insideStartTop"  # over the low northern bars, clear of the tall southern ones
    option["series"][0]["markLine"] = mark_line
    return bundle.Figure(option, ds, title="One zonal price against a price per bus",
                         caption="The zonal market gives everyone the same price. Nodal prices tell the truth "
                         "about the grid: cheap in the north, which makes more than the lines can export, "
                         "expensive in the south, which is short.")


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    nodal, market, rd = nets["nodal"], nets["zonal market"], nets["redispatch"]
    stages_ = ["nodal", "zonal market", "zonal + redispatch"]
    option, ds = charts.bars(stages_, {"cost": [round(_cost(nodal) / 1e3, 1), round(_cost(market) / 1e3, 1), round(_cost(rd) / 1e3, 1)]}, "kEUR/day", category_name="stage")
    cc = bundle.Figure(option, ds, title="Daily system cost by market design",
                       caption="The zonal market looks cheapest because it ignores the bottleneck; once the operator "
                       "pays for redispatch the day costs more than nodal pricing would have.")
    up = {name: float(rd.generators_t.p[f"{name} up"].sum()) for name in GENS}
    down = {name: float(-rd.generators_t.p[f"{name} down"].sum()) for name in GENS}
    option, ds = charts.bars(list(GENS), {"ramp up": [round(up[g], 1) for g in GENS], "ramp down": [round(-down[g], 1) for g in GENS]}, "MWh", category_name="unit")
    vol = bundle.Figure(option, ds, title="Redispatch volumes by unit",
                        caption="Northern wind is turned down and southern gas turned up so the north-south lines "
                        "hold. Volumes are what the market schedule got wrong about the grid.")
    loading = pd.DataFrame({ln: (market.lines_t.p0[ln].abs() / (market.lines.s_nom[ln] / 100) * 100).round(1) for ln in LINES})
    option, ds = charts.time_series(loading, "% of limit")
    option["series"][0]["markLine"] = {**charts.mark_lines([{"value": 100, "label": "limit"}], axis="yAxis")}
    ll = bundle.Figure(option, ds, title="Line loading implied by the zonal schedule",
                       caption="Flows the market schedule would push through the real grid: the two north-south "
                       "lines run far above their limit, which is the redispatch need.")
    return {"redispatch_geography": redispatch_geography(market), "redispatch_intuition": redispatch_intuition(market),
            "price_by_bus": price_by_bus(nodal, market),
            "cost_comparison": cc, "redispatch_volume": vol, "line_loading": ll}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = stages()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
