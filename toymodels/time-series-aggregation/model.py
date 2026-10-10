# SPDX-License-Identifier: MIT
"""time-series-aggregation: how much of a year can be thrown away before the plan changes?

The year-long single-node expansion (wind, solar, gas, battery, hydrogen, 20 % CO2 cap)
solved at its full 4-hourly resolution, then with 12-hour averaging, then with two and
four representative fortnights weighted up to a year. Capacities, cost and the price
duration curve are compared against the full run, along with solve time.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402

SLUG = "time-series-aggregation"
TITLE = "Time series aggregation"

BASE = run.load_model("capacity-expansion-single-node")
CAP_FRACTION = 0.2
CARRIERS = BASE.CARRIERS_MW
FOUR_WEEKS = (("2025-01-08", 14), ("2025-04-08", 14), ("2025-07-08", 14), ("2025-10-08", 14))


def _subset(n: pypsa.Network, index: pd.DatetimeIndex, weight: float) -> pypsa.Network:
    """Keep only `index` of a built year-long network and weight each snapshot by `weight`."""
    m = n.copy()
    m.set_snapshots(index)
    m.snapshot_weightings.loc[:, :] = weight
    return m


def _averaged(n: pypsa.Network, hours: int) -> pypsa.Network:
    """Average every time series over `hours`-long blocks (a coarser regular resolution)."""
    m = n.copy()
    rule = f"{hours}h"
    new_index = n.snapshots.to_series().resample(rule).first().index
    m.set_snapshots(new_index)
    for attr, df in (("p_set", n.loads_t.p_set), ("p_max_pu", n.generators_t.p_max_pu)):
        agg = df.resample(rule).mean()
        target = getattr(m, "loads_t" if attr == "p_set" else "generators_t")
        for col in agg.columns:
            target[attr][col] = agg[col].reindex(new_index).to_numpy()
    m.snapshot_weightings.loc[:, :] = hours
    return m


def build(*, co2_cap_t: float | None = None) -> pypsa.Network:
    return BASE.build(co2_cap_t=co2_cap_t)


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def variants(cap_t: float) -> dict[str, pypsa.Network]:
    full = build(co2_cap_t=cap_t)
    idx2, w2 = profiles.representative_weeks(every=BASE.EVERY_H)
    idx4, w4 = profiles.representative_weeks(every=BASE.EVERY_H, weeks=FOUR_WEEKS)
    return {
        "full 4-hourly": full,
        "12-hour means": _averaged(build(co2_cap_t=cap_t), 12),
        "two fortnights": _subset(build(co2_cap_t=cap_t), idx2, w2),
        "four fortnights": _subset(build(co2_cap_t=cap_t), idx4, w4),
    }


def runs() -> dict:
    ref = solve(build())
    cap_t = CAP_FRACTION * BASE.emissions_t(ref)
    out = {}
    for label, n in variants(cap_t).items():
        t0 = time.perf_counter()
        solve(n)
        out[label] = {"net": n, "solve_s": time.perf_counter() - t0, "snapshots": len(n.snapshots)}
    return out


def numbers(res: dict) -> dict:
    full = res["full 4-hourly"]["net"]
    cap_full = BASE.capacities_mw(full)
    out = {}
    for label, r in res.items():
        n = r["net"]
        cap = BASE.capacities_mw(n)
        out[label] = {
            "snapshots": r["snapshots"],
            "solve_s": round(r["solve_s"], 2),
            "cost_meur_a": float(n.objective / 1e6),
            "cost_error_pct": float(100 * (n.objective - full.objective) / full.objective),
            "capacity_mw": {c: float(cap[c]) for c in CARRIERS},
            "capacity_error_pct": {c: float(100 * (cap[c] - cap_full[c]) / cap_full[c]) if cap_full[c] > 1e-3 else None for c in CARRIERS},
            "h2_store_mwh": float(n.stores.e_nom_opt.get(names.unit("H2 Store"), 0.0)),
            "co2_price_eur_t": float(-n.global_constraints.mu["co2_limit"]),
            "load_weighted_price_eur_mwh": float((n.buses_t.marginal_price["electricity"] * n.loads_t.p_set["demand"] * n.snapshot_weightings.generators).sum()
                                                 / (n.loads_t.p_set["demand"] * n.snapshot_weightings.generators).sum()),
        }
    return out


AVERAGING_WEEK = ("2025-09-08", "2025-09-15")  # the week the intuition figure draws: net load crosses zero every day


def averaging_intuition(res: dict) -> bundle.Figure:
    """A summer week of net load (load minus the wind and solar the full plan builds) at the
    model's own 4-hour resolution against 12-hour means: the daily swing a battery lives on
    is averaged away."""
    n = res["full 4-hourly"]["net"]
    cap = names.plain(n.generators.p_nom_opt)
    avail = names.plain(n.generators_t.p_max_pu)
    net = n.loads_t.p_set["demand"] - avail["onwind"] * cap["onwind"] - avail["solar"] * cap["solar"]
    week = net.loc[AVERAGING_WEEK[0]:AVERAGING_WEEK[1]].iloc[:-1]
    coarse = week.resample("12h").mean().reindex(week.index, method="ffill")
    df = pd.DataFrame({"every 4 hours": week.round(1), "12-hour means": coarse.round(1)})
    option, ds = charts.time_series(df, "MW, load minus wind and solar", step="end", slider=False)
    option["series"][0]["lineStyle"] = {"color": "#6b7280", "width": 1.5}
    option["series"][0]["itemStyle"] = {"color": "#6b7280"}
    option["series"][0]["areaStyle"] = {"color": "#6b7280", "opacity": 0.12}
    option["series"][1]["lineStyle"] = {"color": charts.BAND_ABOVE, "width": 3}
    option["series"][1]["itemStyle"] = {"color": charts.BAND_ABOVE}
    swing = float((week.resample("D").max() - week.resample("D").min()).mean())
    swing_coarse = float((coarse.resample("D").max() - coarse.resample("D").min()).mean())
    return bundle.Figure(
        option, ds, title="What averaging throws away",
        caption=f"A September week of load minus the wind and solar the full-resolution plan builds: below zero there is "
        f"power to spare, above zero something else must supply. Every 4 hours it swings by about {swing:.0f} MW a day, "
        f"surplus at midday and shortfall at night; averaged over 12 hours the swing shrinks to about {swing_coarse:.0f} "
        "MW, and the battery that would move the midday surplus into the night looks useless.",
    )


def figures(res: dict) -> dict[str, bundle.Figure]:
    labels = list(res)
    caps = {c: [round(float(BASE.capacities_mw(r["net"])[c]), 1) for r in res.values()] for c in CARRIERS}
    option, ds = charts.bars(labels, caps, "MW", category_name="aggregation")
    cap = bundle.Figure(option, ds, title="Optimal capacity by aggregation method",
                        caption="Averaging over 12 hours flattens the daily solar peak and the battery disappears; "
                        "representative fortnights keep the diurnal shape but miss the year's extremes, so the "
                        "hydrogen store and the firm capacity move.")
    costs = {"cost": [round(float(r["net"].objective / 1e6), 2) for r in res.values()],
             "solve time x 1": [round(r["solve_s"], 2) for r in res.values()]}
    option, ds = charts.bars(labels, {"cost": costs["cost"]}, "MEUR/a", category_name="aggregation")
    cost = bundle.Figure(option, ds, title="Annual system cost by aggregation method",
                         caption="The total cost of each method against the full resolution: averaging comes out low, "
                         "because it smooths away the hard hours; the representative fortnights come out high, by an amount "
                         "that depends on which weeks they include.")
    curves = {label: r["net"].buses_t.marginal_price["electricity"] for label, r in res.items()}
    option, ds = charts.duration_curves(curves, "EUR/MWh")
    option["yAxis"]["max"] = 400
    pdc = bundle.Figure(option, ds, title="Price duration curves by aggregation method",
                        caption="Axis clipped at 400 EUR/MWh. The coarse methods lose the scarcity spike and the "
                        "zero-price tail alike; both matter for anything that earns on price spreads.")
    return {"averaging_intuition": averaging_intuition(res), "capacity_by_method": cap, "cost_by_method": cost, "price_duration_by_method": pdc}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    res = runs()
    nums = numbers(res)
    figs = figures(res)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
