# SPDX-License-Identifier: MIT
"""merit-order-dispatch: one bus, five thermal generators, one day of hourly load.

The cheapest units run first; the price in every hour is the marginal cost of the
most expensive unit that had to run. Nothing is extendable, so this is pure economic
dispatch, the smallest problem PyPSA solves.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402

SLUG = "merit-order-dispatch"
TITLE = "Merit order and marginal pricing"

# carrier id -> (capacity MW, marginal cost EUR/MWh); ids are pypsa-eur carrier ids
FLEET: dict[str, tuple[float, float]] = {
    "nuclear": (2000, 10),
    "lignite": (3000, 25),
    "CCGT": (4000, 55),
    "OCGT": (2000, 110),
    "oil": (1000, 180),
}
BASE_MW, PEAK_MW = 5000, 10500
VOLL = 3000  # EUR/MWh, load shedding as the last step of the stack


def build(*, base_mw: float = BASE_MW, peak_mw: float = PEAK_MW, fleet: dict | None = None) -> pypsa.Network:
    fleet = fleet or FLEET
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(1))
    n.add("Carrier", list(fleet) + ["load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, (p_nom, mc) in fleet.items():
        n.add("Generator", names.gen(carrier), bus="grid", carrier=carrier, p_nom=p_nom, marginal_cost=mc)
    n.add("Generator", names.gen("load shedding"), bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=VOLL)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, base_mw, peak_mw))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def numbers(n: pypsa.Network) -> dict[str, float]:
    price = n.buses_t.marginal_price["grid"]
    load = n.loads_t.p_set["demand"]
    dispatch = names.plain(n.generators_t.p)
    mc = names.plain(n.generators.marginal_cost)
    rent = ((price.to_numpy()[:, None] - mc.to_numpy()[None, :]) * dispatch).sum()
    marginal = (dispatch.gt(1e-3) & dispatch.lt(names.plain(n.generators.p_nom) - 1e-3)).sum()
    return {
        "total_cost_eur": float(n.objective),
        "avg_price_eur_mwh": float((price * load).sum() / load.sum()),
        "peak_price_eur_mwh": float(price.max()),
        "min_price_eur_mwh": float(price.min()),
        "consumer_payment_eur": float((price * load).sum()),
        "producer_rent_eur": {c: float(rent[c]) for c in FLEET},
        "hours_marginal": {c: int(marginal[c]) for c in FLEET},
        "peak_load_mw": float(load.max()),
        "load_shed_mwh": float(dispatch["load shedding"].sum()),
    }


def merit_order_rent(n: pypsa.Network) -> bundle.Figure:
    """The staircase at the evening peak: where the load cuts it sets one price for every
    unit, and what the cheaper units earn above their own cost is their rent."""
    price = n.buses_t.marginal_price["grid"]
    load = n.loads_t.p_set["demand"]
    peak = load.idxmax()
    q, p = float(load[peak]), float(price[peak])
    gens = names.plain(n.generators).loc[list(FLEET)].sort_values("marginal_cost")
    x1 = gens.p_nom.cumsum()
    x0 = x1 - gens.p_nom
    curves = [charts.Curve(g, [float(x0[g]), float(x1[g])], [float(gens.marginal_cost[g])] * 2, width=4) for g in gens.index]
    # the running cost under the staircase and the rent above it, both up to the load
    xs: list[float] = []
    steps: list[float] = []
    for g in gens.index:
        if x0[g] >= q:
            break
        xs += [float(x0[g]), float(min(x1[g], q))]
        steps += [float(gens.marginal_cost[g])] * 2
    zeros = [0.0] * len(xs)
    flat = [p] * len(xs)
    marginal = gens.index[(x0 < q) & (x1 >= q)][0]
    option, ds = charts.xy_areas(
        curves,
        [charts.Area("running cost", xs, zeros, steps, "#56b4e9"),
         charts.Area("producer rent", xs, steps, flat, charts.BAND_BELOW)],
        [charts.Point(f"price set by {marginal}", q, p, label=f"price {p:.0f} EUR/MWh", color=charts.BAND_ABOVE,
                      label_position="top")],
        x_name="Cumulative capacity (MW)",
        units="EUR/MWh",
        x_marks=[{"value": round(q), "label": "evening peak load"}],
        x_max=float(x1.max()),
        y_max=200,
    )
    return bundle.Figure(
        option, ds, title="One price for all: what the last unit needed sets",
        caption=f"The fleet sorted by running cost at the evening peak ({q:,.0f} MW). The load cuts the "
        f"{marginal} step, so every unit is paid {p:.0f} EUR/MWh; the green area is what the cheaper units "
        "earn above their own cost.",
    )


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    price = n.buses_t.marginal_price["grid"]
    load = n.loads_t.p_set["demand"]
    gens = names.plain(n.generators).loc[list(FLEET)].sort_values("marginal_cost")
    x1 = gens.p_nom.cumsum()
    segments = pd.DataFrame({"x0": x1 - gens.p_nom, "x1": x1, "y": gens.marginal_cost, "name": gens.index})
    option, ds = charts.step_curve(
        segments,
        "Cumulative capacity (MW)",
        "EUR/MWh",
        marks=[{"value": float(load.min()), "label": "min load"}, {"value": float(load.max()), "label": "peak load"}],
    )
    merit = bundle.Figure(
        option, ds, title="Merit order curve",
        caption="Generators sorted by marginal cost; the dashed lines mark the day's minimum and peak load, "
        "and the step they cut sets the price in that hour.",
    )
    stack = names.plain(n.generators_t.p)[list(FLEET)].round(1)
    option, ds = charts.time_series(stack, "MW", stack=True, area=True)
    dispatch = bundle.Figure(option, ds, title="Dispatch stack", caption="Hourly dispatch stacked in merit order; the load line is the top of the stack.")
    option, ds = charts.time_series(pd.DataFrame({"price": price.round(2)}), "EUR/MWh", step="end")
    prices = bundle.Figure(option, ds, title="Hourly price", caption="The marginal cost of the last unit dispatched in each hour, the dual of the bus balance.")
    return {"merit_order_rent": merit_order_rent(n), "merit_order_curve": merit, "dispatch_stack": dispatch, "price_series": prices}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
