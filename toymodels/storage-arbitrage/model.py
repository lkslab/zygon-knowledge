# SPDX-License-Identifier: MIT
"""storage-arbitrage: a small battery in a market whose price is set by a thermal fleet
and a week of variable wind.

The battery is a price-taker: it charges in the cheap wind hours and discharges at the
evening peak. Its revenue is the price spread it captures, net of round-trip losses.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402

SLUG = "storage-arbitrage"
TITLE = "Battery arbitrage against a price-forming fleet"

FLEET = {"nuclear": (2000, 10), "lignite": (2500, 25), "CCGT": (3000, 55), "OCGT": (3000, 110)}
WIND_MW = 6000
BASE_MW, PEAK_MW = 5000, 10000
BATTERY = dict(p_nom=500, max_hours=4, efficiency_store=0.95, efficiency_dispatch=0.95)
DAYS = 7


def build(*, battery_mw: float = 500, max_hours: float = 4, wind_mw: float = WIND_MW) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(DAYS))
    n.add("Carrier", list(FLEET) + ["onwind", "battery", "load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, (p_nom, mc) in FLEET.items():
        n.add("Generator", names.gen(carrier), bus="grid", carrier=carrier, p_nom=p_nom, marginal_cost=mc)
    n.add("Generator", names.gen("onwind"), bus="grid", carrier="onwind", p_nom=wind_mw, marginal_cost=0,
          p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", names.gen("load shedding"), bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=3000)
    n.add("StorageUnit", names.unit("battery"), bus="grid", carrier="battery", cyclic_state_of_charge=True,
          marginal_cost=0.5, **{**BATTERY, "p_nom": battery_mw, "max_hours": max_hours})
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def numbers(n: pypsa.Network) -> dict:
    price = n.buses_t.marginal_price["grid"]
    p = n.storage_units_t.p[names.unit("battery")]  # + discharging, - charging
    dispatch, store = p.clip(lower=0), (-p).clip(lower=0)
    cap = n.storage_units.loc[names.unit("battery")]
    energy_cap = cap.p_nom * cap.max_hours
    daily = pd.DataFrame({"price": price, "p": p}).groupby(price.index.date)
    return {
        "revenue_eur": float((price * p).sum()),
        "revenue_per_mw_eur": float((price * p).sum() / cap.p_nom),
        "full_cycles": float(dispatch.sum() / energy_cap),
        "round_trip_loss_pct": float(100 * (1 - dispatch.sum() / store.sum())) if store.sum() > 0 else None,
        "avg_charge_price_eur_mwh": float((price * store).sum() / store.sum()) if store.sum() > 0 else None,
        "avg_discharge_price_eur_mwh": float((price * dispatch).sum() / dispatch.sum()) if dispatch.sum() > 0 else None,
        "mean_daily_price_spread_eur_mwh": float(daily["price"].agg(lambda s: s.max() - s.min()).mean()),
        "avg_price_eur_mwh": float(price.mean()),
        "wind_share_pct": float(100 * n.generators_t.p[names.gen("onwind")].sum() / n.loads_t.p_set["demand"].sum()),
        "wind_curtailed_mwh": float((n.generators_t.p_max_pu[names.gen("onwind")] * WIND_MW - n.generators_t.p[names.gen("onwind")]).sum()),
    }


def arbitrage_intuition(n: pypsa.Network) -> bundle.Figure:
    """The week's price with the hours the battery buys and sells filled under it, and the
    average price of each: the gap between the two lines is what it lives on."""
    price = n.buses_t.marginal_price["grid"]
    p = n.storage_units_t.p[names.unit("battery")]
    buy, sell = p < -1e-3, p > 1e-3
    df = pd.DataFrame({
        "price": price.round(2),
        "hours it buys (charges)": price.where(buy).round(2),
        "hours it sells (discharges)": price.where(sell).round(2),
    })
    option, ds = charts.time_series(df, "EUR/MWh", step="middle", slider=False)
    colours = {"hours it buys (charges)": "#56b4e9", "hours it sells (discharges)": charts.BAND_BELOW}
    for s in option["series"]:
        if s["name"] in colours:
            c = colours[s["name"]]
            s.update({"itemStyle": {"color": c}, "lineStyle": {"width": 0, "opacity": 0}, "connectNulls": False,
                      "areaStyle": {"color": c, "opacity": 0.55}, "silent": True})
        else:
            s["lineStyle"] = {**s.get("lineStyle", {}), "color": "#6b7280", "width": 1.5}
            s["itemStyle"] = {"color": "#6b7280"}
    energy_in, energy_out = (-p).clip(lower=0), p.clip(lower=0)
    buy_at = float((price * energy_in).sum() / energy_in.sum())
    sell_at = float((price * energy_out).sum() / energy_out.sum())
    option["series"][0]["markLine"] = charts.mark_lines([{"value": round(buy_at, 1), "label": f"buys at {buy_at:.0f} on average"},
                                                          {"value": round(sell_at, 1), "label": f"sells at {sell_at:.0f} on average"}],
                                                         axis="yAxis")
    return bundle.Figure(
        option, ds, title="Buy low, sell high: what a battery lives on",
        caption=f"The week's price: about 25 EUR/MWh when it is windy, 55 most of the time, 110 at a few evening peaks. "
        f"The battery charges in the blue "
        f"hours and discharges in the green ones: it buys at about {buy_at:.0f} EUR/MWh on average and sells at about "
        f"{sell_at:.0f}. Round-trip losses take about a tenth of what it stores, so the spread has to beat that.",
    )


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    price = n.buses_t.marginal_price["grid"].round(2)
    p = n.storage_units_t.p[names.unit("battery")].round(1)
    df = pd.DataFrame({"battery": p, "price": price})
    option, ds = charts.dual_axis(df, ["battery"], ["price"], "MW", "EUR/MWh", left_area=True, step="middle")
    charge = bundle.Figure(option, ds, title="Battery power against the price",
                           caption="Positive is discharge, negative is charge. The battery buys the cheap windy hours and sells the evening peak.")
    soc = pd.DataFrame({"battery": n.storage_units_t.state_of_charge[names.unit("battery")].round(1)})
    option, ds = charts.time_series(soc, "MWh")
    soc_fig = bundle.Figure(option, ds, title="State of charge", height=280, caption="Cyclic: the week ends where it started.")
    rev = (price * p).groupby(price.index.date).sum().round(0)
    days = [d.strftime("%a %d") for d in rev.index]
    option, ds = charts.bars(days, {"revenue": rev.tolist()}, "EUR", horizontal=False, category_name="day")
    rev_fig = bundle.Figure(option, ds, title="Daily arbitrage revenue", caption="Revenue is the daily price spread the battery captures; windy days with a deep trough pay best.")
    return {"arbitrage_intuition": arbitrage_intuition(n), "charge_vs_price": charge, "state_of_charge": soc_fig, "daily_revenue": rev_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
