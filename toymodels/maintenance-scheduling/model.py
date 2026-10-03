# SPDX-License-Identifier: MIT
"""maintenance-scheduling: when should a plant take its three-day outage?

Three thermal units and two weeks of load with a weekend dip. The coal unit must be
off for 72 consecutive hours somewhere in the fortnight; PyPSA's native maintenance
attributes turn that into binary start variables and pick the window that costs least.
The same outage forced into the first days shows what a badly timed one costs.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402

SLUG = "maintenance-scheduling"
TITLE = "Maintenance scheduling"

UNITS = {"coal": (1000, 30), "CCGT": (800, 60), "OCGT": (600, 120)}
MAINTAINED = "coal"
DURATION_H = 72
DAYS = 14
BASE_MW, PEAK_MW = 600, 1300
FORCED_START_H = 24  # the forced-timing case: outage from hour 24 for DURATION_H hours


def build(*, forced_start: int | None = None) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(DAYS))
    n.add("Carrier", list(UNITS) + ["load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, (p_nom, mc) in UNITS.items():
        n.add("Generator", names.gen(carrier), bus="grid", carrier=carrier, p_nom=p_nom, marginal_cost=mc)
    n.add("Generator", names.gen("load shedding"), bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=3000)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW, weekend_factor=0.75))
    if forced_start is None:
        n.generators.loc[names.gen(MAINTAINED), ["maintainable", "maintenance_duration", "maintenance_pu", "maintenance_events"]] = [True, DURATION_H, 1.0, 1]
    else:
        avail = pd.Series(1.0, index=n.snapshots)
        avail.iloc[forced_start:forced_start + DURATION_H] = 0.0
        n.generators_t.p_max_pu[names.gen(MAINTAINED)] = avail
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n, solver_options={"mip_rel_gap": 1e-6})


def outage_window(n: pypsa.Network) -> tuple[pd.Timestamp, pd.Timestamp]:
    has = "maintenance" in n.generators_t and names.gen(MAINTAINED) in n.generators_t.maintenance.columns
    m = n.generators_t.maintenance[names.gen(MAINTAINED)] if has else (1 - n.generators_t.p_max_pu[names.gen(MAINTAINED)])
    on = m[m > 0.5].index
    return on[0], on[-1]


def availability(n: pypsa.Network) -> pd.DataFrame:
    df = pd.DataFrame(1, index=n.snapshots, columns=list(UNITS))
    if "maintenance" in n.generators_t and names.gen(MAINTAINED) in n.generators_t.maintenance.columns:
        df[MAINTAINED] = (1 - n.generators_t.maintenance[names.gen(MAINTAINED)]).round().astype(int)
    elif names.gen(MAINTAINED) in n.generators_t.p_max_pu:
        df[MAINTAINED] = n.generators_t.p_max_pu[names.gen(MAINTAINED)].round().astype(int)
    return df


def runs() -> dict[str, pypsa.Network]:
    return {"optimal timing": solve(build()), "forced timing": solve(build(forced_start=FORCED_START_H))}


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    opt, forced = nets["optimal timing"], nets["forced timing"]
    w0, w1 = outage_window(opt)
    f0, f1 = outage_window(forced)
    load = opt.loads_t.p_set["demand"]
    return {
        "chosen_window": {"start": str(w0), "end": str(w1), "weekday_start": w0.day_name()},
        "forced_window": {"start": str(f0), "end": str(f1)},
        "cost_optimal_eur": float(opt.objective),
        "cost_forced_eur": float(forced.objective),
        "saving_eur": float(forced.objective - opt.objective),
        "saving_pct": float(100 * (forced.objective - opt.objective) / forced.objective),
        "mean_load_in_window_mw": {"optimal": float(load.loc[w0:w1].mean()), "forced": float(load.loc[f0:f1].mean())},
        "peaker_energy_mwh": {k: float(n.generators_t.p[names.gen("OCGT")].sum()) for k, n in nets.items()},
        "load_shed_mwh": {k: float(n.generators_t.p[names.gen("load shedding")].sum()) for k, n in nets.items()},
        "avg_price_eur_mwh": {k: float((_prices(n) * load).sum() / load.sum()) for k, n in nets.items()},
        "duration_h": DURATION_H,
    }


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    opt, forced = nets["optimal timing"], nets["forced timing"]
    avail = availability(opt)
    avail.columns = [f"{c}" for c in avail.columns]
    option, ds = charts.status_steps(avail)
    av = bundle.Figure(option, ds, title="Unit availability, optimal timing", height=240,
                       caption="One band per unit, raised while available; the coal band drops for the 72 hours the "
                       "solver chose, over the weekend trough where its absence costs least.")
    stack = names.plain(opt.generators_t.p)[list(UNITS)].round(1)
    option, ds = charts.time_series(stack, "MW", stack=True, area=True)
    disp = bundle.Figure(option, ds, title="Dispatch with the optimal outage",
                         caption="While coal is out the gas units cover it; the peaker runs only at the weekday evening peaks.")
    load = opt.loads_t.p_set["demand"]
    prices = pd.DataFrame({"optimal timing": _prices(opt), "forced timing": _prices(forced)}).round(2)
    option, ds = charts.time_series(prices, "EUR/MWh", step="end")
    pr = bundle.Figure(option, ds, title="Price, optimal vs forced outage timing",
                       caption="Prices from a linear re-solve with the chosen outage fixed. The forced outage lands "
                       "on weekdays and puts the peaker on the margin for whole days.")
    option, ds = charts.bars(list(nets), {"dispatch cost": [round(float(opt.objective) / 1e3, 1), round(float(forced.objective) / 1e3, 1)]}, "kEUR", category_name="timing")
    cost = bundle.Figure(option, ds, title="Fortnight cost by outage timing", caption="The saving from choosing the window is the value of scheduling.")
    return {"unit_availability": av, "dispatch_stack": disp, "price_series": pr, "cost_comparison": cost}


def _prices(n: pypsa.Network) -> pd.Series:
    """The MILP has no duals; re-solve as an LP with the chosen outage fixed."""
    m = build(forced_start=0)
    m.generators_t.p_max_pu[names.gen(MAINTAINED)] = availability(n)[MAINTAINED].astype(float)
    run.solve(m)
    return m.buses_t.marginal_price["grid"]


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
