# SPDX-License-Identifier: MIT
"""transmission-expansion: how much line to build between a windy zone and a load
centre, and how the answer moves with the cost of transmission.

Two zones joined by one extendable bidirectional link. The north has cheap wind and
little load; the south has the demand and a gas fleet. Sweeping the link's annualised
cost per MW shows the trade-off between building wires, building gas in the south
and curtailing wind in the north, and checks that at the optimum the link's
congestion rent exactly pays for it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, geography, profiles, run  # noqa: E402

SLUG = "transmission-expansion"
TITLE = "Transmission expansion between a windy and a load-rich zone"

BASE = run.load_model("capacity-expansion-single-node")
LINK_COST_CASES: dict[str, float | None] = {"50 kEUR": 50_000, "100 kEUR": 100_000, "200 kEUR": 200_000, "400 kEUR": 400_000, "no link": None}
LOAD_MW = {"north": 20, "south": 80}  # mean load
WIND_NORTH_MW = 400  # existing wind in the north, cost sunk
GAS_SOUTH_MW = 60  # existing gas in the south
OCGT_NORTH_MW = 30  # small existing peaker in the north, so the no-link case is not about lost load
LINK_MAX_MW = 500
MAP_CASE = "100 kEUR"  # the link cost the map draws

# the two zones as a made-up country: a windy, thinly populated north, the cities in the south
OUTLINE = [(1.5, 13.2), (3.5, 13.9), (5.5, 13.5), (7.5, 14.0), (9.5, 13.4), (10.8, 12.6), (10.5, 10.8),
           (11.0, 9.0), (10.6, 7.2), (11.1, 5.4), (10.7, 3.4), (9.6, 1.6), (7.6, 0.9), (5.6, 1.2), (3.6, 0.7),
           (1.8, 1.4), (1.1, 3.2), (1.5, 5.0), (1.0, 6.8), (1.4, 8.6), (0.9, 10.4), (1.2, 12.0)]
CUT = [(-1, 7.3), (3.0, 7.8), (6.0, 7.1), (9.0, 7.7), (12, 7.2)]
ANCHORS = {"north": (6.0, 10.5), "south": (6.0, 4.0)}
LABEL_AT = {"north": (5.4, 12.4), "south": (5.4, 2.4)}


def _capex(tech: str) -> float:
    t = BASE.TECH[tech]
    return finance.capital_cost(t["overnight"], t["life"], fom_pct=t["fom"])


def build(*, link_cost: float | None = 100_000) -> pypsa.Network:
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "DC", "onwind", "solar", "load shedding", "battery"])
    n.add("Carrier", "OCGT", co2_emissions=BASE.CO2_CCGT * 1.3)
    n.add("Carrier", "CCGT", co2_emissions=BASE.CO2_CCGT)
    n.add("Bus", ["north", "south"], carrier="AC")
    load = profiles.annual_load(year, 1.0).loc[index]
    for zone, mw in LOAD_MW.items():
        n.add("Load", f"load {zone}", bus=zone, carrier="load", p_set=load * mw)
        n.add("Generator", f"shed {zone}", bus=zone, carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    n.add("Generator", "onwind north", bus="north", carrier="onwind", p_nom=WIND_NORTH_MW, marginal_cost=0.1,
          p_max_pu=profiles.wind(year, mean_cf=0.4).loc[index])
    n.add("Generator", "OCGT north", bus="north", carrier="OCGT", p_nom=OCGT_NORTH_MW, marginal_cost=120.0)
    n.add("Generator", "CCGT south", bus="south", carrier="CCGT", p_nom=GAS_SOUTH_MW, p_nom_extendable=True, p_nom_min=GAS_SOUTH_MW,
          capital_cost=_capex("CCGT"), marginal_cost=BASE.TECH["CCGT"]["marginal_cost"])
    n.add("Generator", "solar south", bus="south", carrier="solar", p_nom_extendable=True, capital_cost=_capex("solar"),
          p_max_pu=profiles.solar(year).loc[index])
    b = BASE.TECH["battery"]
    n.add("StorageUnit", "battery south", bus="south", carrier="battery", p_nom_extendable=True, capital_cost=_capex("battery"),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
    if link_cost is not None:
        n.add("Link", "north-south", bus0="north", bus1="south", carrier="DC", p_nom_extendable=True, p_min_pu=-1,
              p_nom_max=LINK_MAX_MW, capital_cost=link_cost, efficiency=0.97)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def sweep() -> dict[str, pypsa.Network]:
    return {label: solve(build(link_cost=cost)) for label, cost in LINK_COST_CASES.items()}


def summary(n: pypsa.Network, link_cost: float | None) -> dict:
    w = n.snapshot_weightings.generators
    price = n.buses_t.marginal_price
    spread = price["south"] - price["north"]
    has_link = "north-south" in n.links.index
    p_link = n.links_t.p0["north-south"] if has_link else pd.Series(0.0, index=n.snapshots)
    cap = float(n.links.p_nom_opt["north-south"]) if has_link else 0.0
    # what the link earns: delivered power sold at the receiving bus minus power bought at the sending bus
    p1 = n.links_t.p1["north-south"] if has_link else pd.Series(0.0, index=n.snapshots)
    rent = float(((-p1) * price["south"] * w).sum() - (p_link * price["north"] * w).sum()) if has_link else 0.0
    wind_avail = float((n.generators_t.p_max_pu["onwind north"] * WIND_NORTH_MW * w).sum())
    wind = float((n.generators_t.p["onwind north"] * w).sum())
    cr = finance.cost_recovery(n).reindex(["CCGT", "OCGT", "solar", "battery", "onwind", "load shedding"]).fillna(0.0)
    gen_capex = float(cr.loc[["CCGT", "solar", "battery"], "capex"].sum())
    opex = float(cr.loc[["CCGT", "OCGT", "onwind", "load shedding"], "opex"].sum())
    link_capex = cap * link_cost if (has_link and link_cost) else 0.0
    return {
        "link_mw": cap,
        "link_full_load_hours": float((p_link.abs() * w).sum() / cap) if cap > 1e-3 else None,
        "wind_curtailment_pct": float(100 * (1 - wind / wind_avail)),
        "mean_price_spread_eur_mwh": float((spread * w).sum() / w.sum()),
        "congestion_rent_meur_a": rent / 1e6,
        "link_cost_recovery_ratio": float(rent / link_capex) if link_capex > 0 else None,
        "gas_south_mw": float(n.generators.p_nom_opt["CCGT south"]),
        "solar_south_mw": float(n.generators.p_nom_opt["solar south"]),
        "battery_south_mw": float(n.storage_units.p_nom_opt["battery south"]),
        "cost_meur_a": {"transmission": link_capex / 1e6, "generation capex": gen_capex / 1e6, "opex": opex / 1e6, "total": float(n.objective / 1e6)},
        "share_hours_link_at_limit_pct": float(100 * ((p_link.abs() >= cap - 1e-3).astype(float) * w).sum() / w.sum()) if cap > 1e-3 else None,
    }


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    out = {label: summary(n, LINK_COST_CASES[label]) for label, n in nets.items()}
    out["saving_vs_no_link_meur_a"] = {label: out["no link"]["cost_meur_a"]["total"] - out[label]["cost_meur_a"]["total"] for label in nets if label != "no link"}
    return out


def transmission_geography(nets: dict[str, pypsa.Network]) -> bundle.Figure:
    """The two zones as a made-up country: the wind the north has to spare in its windiest
    hours against the link the optimum builds, at its width on the same scale."""
    n = nets[MAP_CASE]
    s = summary(n, LINK_COST_CASES[MAP_CASE])
    w = n.snapshot_weightings.generators
    outline, rings = geography.country(OUTLINE, [CUT], ANCHORS)
    load = n.loads_t.p_set
    avail = n.generators_t.p_max_pu["onwind north"] * WIND_NORTH_MW
    surplus = float((avail - load["load north"]).max())
    gen = n.generators_t.p.T.groupby(n.generators.bus).sum().T
    price = n.buses_t.marginal_price
    mean = lambda x: float((x * w).sum() / w.sum())  # noqa: E731
    net = {"north": mean(gen["north"] - load["load north"]), "south": mean(gen["south"] - load["load south"])}
    regions = [
        charts.Region("North", rings["north"], value=round(net["north"], 1), label_at=LABEL_AT["north"],
                      label=f"windy, few people\nwind {WIND_NORTH_MW} MW · demand {LOAD_MW['north']} MW\n"
                      f"mean price {mean(price['north']):.0f} EUR/MWh"),
        charts.Region("South", rings["south"], value=round(net["south"], 1), label_at=LABEL_AT["south"],
                      label=f"cities\ndemand {LOAD_MW['south']} MW · gas {s['gas_south_mw']:.0f} MW · solar {s['solar_south_mw']:.0f} MW\n"
                      f"mean price {mean(price['south']):.0f} EUR/MWh"),
    ]
    north_xy, south_xy = (3.4, 9.6), (3.4, 4.8)
    sites = [charts.Site("onwind north", 7.3, 10.5, WIND_NORTH_MW, carrier="onwind", label="wind farms"),
             charts.Site("CCGT south", 7.3, 4.4, s["gas_south_mw"], carrier="CCGT", label="gas")]
    flow = mean(n.links_t.p0["north-south"])
    link = charts.Link("north-south", north_xy, south_xy, capacity=s["link_mw"], flow=round(flow, 1),
                       label=f"link built: {s['link_mw']:.0f} MW\nfull {s['share_hours_link_at_limit_pct']:.0f} % of hours",
                       label_at=(3.4, 10.5))
    arrow = charts.Arrow("wind to spare", (7.3, 9.7), (7.3, 5.4), value=surplus,
                         label=f"wind to spare in\nthe windiest hours:\nup to {surplus:.0f} MW", label_at=(9.3, 8.9))
    option, ds = charts.region_map(regions, outline=outline, sites=sites, links=[link], arrows=[arrow],
                                   value_name="mean net position", unit="MW", low_label="short of power",
                                   high_label="power to spare", height=560)
    return bundle.Figure(
        option, ds, title="How much wire to a windy region?",
        caption=f"A made-up country with a windy, empty north and a populated south. In its windiest hours the north has "
        f"up to {surplus:.0f} MW of wind to spare (the broad arrow); at {LINK_COST_CASES[MAP_CASE] / 1e3:.0f} kEUR per MW "
        f"and year the optimum builds a {s['link_mw']:.0f} MW link (drawn on the same width scale) and curtails "
        f"{s['wind_curtailment_pct']:.0f} % of the wind: the last MW of a bigger wire would carry power only a few hours a year.",
    )


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    s = {label: summary(n, LINK_COST_CASES[label]) for label, n in nets.items()}
    with_link = [label for label in nets if LINK_COST_CASES[label] is not None]
    df = pd.DataFrame({"link capacity": [s[l]["link_mw"] for l in with_link],
                       "gas south": [s[l]["gas_south_mw"] for l in with_link]},
                      index=pd.Index([LINK_COST_CASES[l] / 1e3 for l in with_link], name="cost")).round(1)
    option, ds = charts.xy_lines(df, "Link cost (kEUR per MW per year)", "MW", symbols=True, x_extra={"min": 0})
    cv = bundle.Figure(option, ds, title="Optimal link and southern gas capacity against link cost",
                       caption="Cheaper wires mean more of them and less gas in the south; the curve flattens where "
                       "the northern wind is fully used and the marginal MW of link only moves curtailed energy.")
    labels = list(nets)
    parts = ("transmission", "generation capex", "opex")
    option, ds = charts.bars(labels, {p: [round(s[l]["cost_meur_a"][p], 3) for l in labels] for p in parts}, "MEUR/a", stack=True, horizontal=False, category_name="link cost")
    tc = bundle.Figure(option, ds, title="System cost by link cost case",
                       caption="Transmission spend against what it saves in southern generation and fuel. "
                       "The no-link case pays with gas and curtailed wind.")
    curves = {l: nets[l].links_t.p0["north-south"] for l in with_link}
    option, ds = charts.duration_curves(curves, "MW, north to south positive")
    fd = bundle.Figure(option, ds, title="Flow duration on the link",
                       caption="Sorted flows: the cheap-link cases run at the limit for many hours and reverse in the "
                       "calm hours when the south's gas serves the north.")
    return {"transmission_geography": transmission_geography(nets), "capacity_vs_cost": cv, "system_cost_tradeoff": tc, "flow_duration": fd}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = sweep()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
