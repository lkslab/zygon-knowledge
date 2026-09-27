# SPDX-License-Identifier: MIT
"""hydro-cascade: two reservoirs in series on one river, a turbine and a spillway at
each, against a thermal backup and an electricity load in a wet and a dry fortnight.

Water is counted in the energy it can make at a turbine. What the upper turbine
releases arrives in the lower reservoir; what the upper spillway lets through arrives
too, without making power. The price of water on each reservoir bus is the water
value: what one more stored unit would save downstream.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "hydro-cascade"
TITLE = "Chained hydro reservoirs: turbines, spill and water values"

WEEKS = (("2025-04-08", 14), ("2025-08-08", 14))  # snowmelt and late-summer drought
RES = {"upper": dict(e_nom=25_000, turbine_mw=80, e_initial_pu=0.5), "lower": dict(e_nom=6_000, turbine_mw=60, e_initial_pu=0.5)}
INFLOW_MEAN_MW = {"upper": 45.0, "lower": 12.0}  # annual mean in MWh-equivalent per hour
CCGT_MW, CCGT_COST = 150.0, 60.0
LOAD_MEAN_MW = 100.0


def inflow(index: pd.DatetimeIndex, mean_mw: float, *, seed: int) -> pd.Series:
    """Snowmelt-shaped inflow: a spring peak in April-May, a dry late summer, some rain noise."""
    rng = np.random.default_rng(seed)
    doy = index.dayofyear.to_numpy()
    melt = np.exp(-((doy - 120) / 25.0) ** 2) * 3.0
    base = 0.35 + 0.25 * np.cos(2 * np.pi * (doy - 60) / 365.25)
    noise = np.clip(1 + 0.35 * rng.standard_normal(len(index)), 0.2, None)
    x = (base + melt) * noise
    return pd.Series(x / x.mean() * mean_mw, index=index, name="inflow")


def build() -> pypsa.Network:
    index, weight = profiles.representative_weeks(weeks=WEEKS)
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "water", "hydro", "CCGT", "load shedding", "spill", "inflow"])
    n.add("Bus", "electricity", carrier="AC")
    n.add("Bus", ["water upper", "water lower", "sea"], carrier="water")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, LOAD_MEAN_MW).loc[index])
    n.add("Generator", "CCGT", bus="electricity", carrier="CCGT", p_nom=CCGT_MW, marginal_cost=CCGT_COST)
    n.add("Generator", "load shedding", bus="electricity", carrier="load shedding", p_nom=1e4, marginal_cost=3000)
    for name, spec in RES.items():
        bus = f"water {name}"
        infl = inflow(year, INFLOW_MEAN_MW[name], seed=42 if name == "upper" else 43).loc[index]
        # inflow is forced: p_min_pu = p_max_pu, the reservoir must take it or spill it
        n.add("Generator", f"inflow {name}", bus=bus, carrier="inflow", p_nom=1.0, p_max_pu=infl, p_min_pu=infl)
        n.add("Store", f"reservoir {name}", bus=bus, carrier="hydro", e_nom=spec["e_nom"], e_initial=spec["e_initial_pu"] * spec["e_nom"], e_cyclic=True)
    n.add("Link", "turbine upper", bus0="water upper", bus1="electricity", bus2="water lower", carrier="hydro",
          p_nom=RES["upper"]["turbine_mw"], efficiency=1.0, efficiency2=1.0)
    n.add("Link", "spill upper", bus0="water upper", bus1="water lower", carrier="spill", p_nom=1e4, efficiency=1.0, marginal_cost=0.01)
    n.add("Link", "turbine lower", bus0="water lower", bus1="electricity", bus2="sea", carrier="hydro",
          p_nom=RES["lower"]["turbine_mw"], efficiency=1.0, efficiency2=1.0)
    n.add("Link", "spill lower", bus0="water lower", bus1="sea", carrier="spill", p_nom=1e4, efficiency=1.0, marginal_cost=0.01)
    n.add("Store", "sea", bus="sea", carrier="water", e_nom=1e9)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def flows(n: pypsa.Network) -> pd.DataFrame:
    L = n.links_t.p0
    return pd.DataFrame({"turbine upper": L["turbine upper"], "spill upper": L["spill upper"],
                         "turbine lower": L["turbine lower"], "spill lower": L["spill lower"]})


def numbers(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    f = flows(n)
    hydro = float(((f["turbine upper"] + f["turbine lower"]) * w).sum())
    demand = float((n.loads_t.p_set["demand"] * w).sum())
    price = n.buses_t.marginal_price
    infl = {r: float((n.generators_t.p[f"inflow {r}"] * w).sum()) for r in RES}
    wv = {r: price[f"water {r}"] for r in RES}
    return {
        "hydro_energy_gwh": hydro / 1e3,
        "hydro_share_pct": float(100 * hydro / demand),
        "inflow_gwh": {r: v / 1e3 for r, v in infl.items()},
        "spill_gwh": {r: float((f[f"spill {r}"] * w).sum() / 1e3) for r in RES},
        "spill_share_of_arrivals_pct": {"upper": float(100 * (f["spill upper"] * w).sum() / infl["upper"]),
                                        "lower": float(100 * (f["spill lower"] * w).sum() / (infl["lower"] + ((f["turbine upper"] + f["spill upper"]) * w).sum()))},
        "water_value_eur_mwh": {r: {"mean": float((wv[r] * w).sum() / w.sum()), "wet_fortnight": float(wv[r].iloc[: len(wv[r]) // 2].mean()), "dry_fortnight": float(wv[r].iloc[len(wv[r]) // 2 :].mean())} for r in RES},
        "electricity_price_eur_mwh": {"mean": float((price["electricity"] * w).sum() / w.sum()), "wet_fortnight": float(price["electricity"].iloc[: len(price) // 2].mean()), "dry_fortnight": float(price["electricity"].iloc[len(price) // 2 :].mean())},
        "thermal_hours_pct": float(100 * (n.generators_t.p["CCGT"] > 1e-3).mean()),
        "thermal_energy_gwh": float((n.generators_t.p["CCGT"] * w).sum() / 1e3),
        "reservoir_level_range_pct": {r: [float(100 * n.stores_t.e[f"reservoir {r}"].min() / RES[r]["e_nom"]), float(100 * n.stores_t.e[f"reservoir {r}"].max() / RES[r]["e_nom"])] for r in RES},
        "load_shed_mwh": float((n.generators_t.p["load shedding"] * w).sum()),
    }


WATER = "#56b4e9"  # sankey colours: water, the turbines (power made on the way), the spillways (none made)
TURBINE = "#0072b2"
SPILL = "#9ca3af"


def cascade_intuition(n: pypsa.Network) -> bundle.Figure:
    """The river's water over the year as a sankey: it enters the upper reservoir, leaves by the
    turbine or the spillway, and either way lands in the lower one, where it meets a second
    turbine. What passes both turbines makes power twice."""
    w = n.snapshot_weightings.generators
    f = flows(n).mul(w, axis=0).sum() / 1e3
    infl = {r: float((n.generators_t.p[f"inflow {r}"] * w).sum() / 1e3) for r in RES}
    tu, su, tl, sl = (float(f[k]) for k in ("turbine upper", "spill upper", "turbine lower", "spill lower"))
    # (name, colour, column): columns pinned so the side streams join where the lower reservoir is
    spec = [
        ("melt and rain", WATER, 0), ("upper reservoir", WATER, 1),
        (f"upper turbine\n{tu:.0f} GWh of power", TURBINE, 2), ("upper spillway", SPILL, 2), ("side streams", WATER, 2),
        ("lower reservoir", WATER, 3),
        (f"lower turbine\n{tl:.0f} GWh of power", TURBINE, 4), ("lower spillway", SPILL, 4), ("river below", WATER, 5),
    ]
    names = [s[0] for s in spec]
    edges = [
        (names[0], names[1], infl["upper"]), (names[1], names[2], tu), (names[1], names[3], su),
        (names[2], names[5], tu), (names[3], names[5], su), (names[4], names[5], infl["lower"]),
        (names[5], names[6], tl), (names[5], names[7], sl), (names[6], names[8], tl), (names[7], names[8], sl),
    ]
    links = [{"source": a, "target": b, "value": round(v, 1)} for a, b, v in edges if v > 0.05]
    option = {
        "tooltip": {"trigger": "item"},
        "series": [{"type": "sankey", "left": 8, "right": 90, "top": 16, "bottom": 16, "nodeGap": 18, "nodeWidth": 16,
                    "data": [{"name": nm, "depth": d, "itemStyle": {"color": c}} for nm, c, d in spec],
                    "links": links, "emphasis": {"focus": "adjacency"},
                    "lineStyle": {"color": "source", "opacity": 0.35, "curveness": 0.5},
                    "nodeAlign": "justify", "label": {"fontSize": 12}}],
    }
    return bundle.Figure(
        option, {}, title="One river, two power stations", height=420,
        caption=f"Water over the year, in the energy a turbine can make from it (GWh). The upper reservoir's water leaves "
        f"by its turbine or its spillway and lands in the lower reservoir either way, so water that goes through the upper "
        f"turbine can make power there and again below: {tu:.0f} and {tl:.0f} GWh from the two turbines. Spilled water "
        "makes none, and a lot of the melt is spilled because the turbines are too small for it.",
    )


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    lvl = pd.DataFrame({f"reservoir {r}": (n.stores_t.e[f"reservoir {r}"] / RES[r]["e_nom"] * 100).round(1) for r in RES})
    option, ds = charts.time_series(lvl, "% full", slider=False)
    levels = bundle.Figure(option, ds, title="Reservoir levels",
                           caption="The large upper reservoir fills through the snowmelt fortnight and is drawn down "
                           "in the dry one; the small lower reservoir cycles daily on what the upper turbine "
                           "passes down. The gap in the middle is the unmodelled summer between the two fortnights.")
    f = flows(n).round(1)
    option, ds = charts.time_series(f, "MW (water in turbine-energy units)", stack=True, area=True, slider=False)
    fl = bundle.Figure(option, ds, title="Turbine and spill flows",
                       caption="Spill appears only when the lower reservoir is full and the turbines are at their "
                       "limit during the melt; in the dry fortnight every unit of water goes through a turbine.")
    price = n.buses_t.marginal_price
    pr = pd.DataFrame({"electricity": price["electricity"], "water upper": price["water upper"], "water lower": price["water lower"]}).round(2)
    option, ds = charts.time_series(pr, "EUR/MWh", slider=False)
    pf = bundle.Figure(option, ds, title="Electricity price and water values",
                       caption="The water bus prices are the marginal values of stored water. In the wet fortnight "
                       "water is nearly free (spill is the alternative); in the dry one it rises to the thermal "
                       "cost it displaces, and the lower reservoir's water is worth less than the upper's because "
                       "it can only pass one turbine.")
    return {"cascade_intuition": cascade_intuition(n), "reservoir_levels": levels, "turbine_and_spill_flows": fl, "prices_and_water_values": pf}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
