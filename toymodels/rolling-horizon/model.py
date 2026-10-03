# SPDX-License-Identifier: MIT
"""rolling-horizon: the same two windy weeks dispatched with perfect foresight and with
a rolling 24-hour window that sees only six hours beyond each day.

The battery is where foresight shows: with the whole fortnight in view it saves charge
for the expensive evenings; with a day at a time it fills and empties on what it can
see. The cost gap between the two is the value of the forecast the rolling solve lacks.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402

SLUG = "rolling-horizon"
TITLE = "Rolling horizon versus perfect foresight"

FLEET = {"nuclear": (2000, 10), "lignite": (2500, 25), "CCGT": (3000, 55), "OCGT": (3000, 110)}
WIND_MW = 6000
BASE_MW, PEAK_MW = 5000, 10000
BATTERY = dict(p_nom=1000, max_hours=8, efficiency_store=0.95, efficiency_dispatch=0.95)
DAYS = 14
CASES = {"rolling 24 h": (24, 0), "rolling 24 h + 6 h overlap": (24, 6)}


def build() -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(DAYS))
    n.add("Carrier", list(FLEET) + ["onwind", "battery", "load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, (p_nom, mc) in FLEET.items():
        n.add("Generator", names.gen(carrier), bus="grid", carrier=carrier, p_nom=p_nom, marginal_cost=mc)
    n.add("Generator", names.gen("onwind"), bus="grid", carrier="onwind", p_nom=WIND_MW, marginal_cost=0, p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", names.gen("load shedding"), bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=3000)
    # not cyclic: a rolling window cannot close a cycle it does not see; both solves start half full
    n.add("StorageUnit", names.unit("battery"), bus="grid", carrier="battery", cyclic_state_of_charge=False,
          state_of_charge_initial=BATTERY["p_nom"] * BATTERY["max_hours"] / 2, marginal_cost=0.5, **BATTERY)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def solve_rolling(n: pypsa.Network, *, horizon: int = 24, overlap: int = 0) -> pypsa.Network:
    """`optimize_with_rolling_horizon`: successive windows of `horizon` snapshots, each
    solved with `overlap` extra snapshots it can see but does not keep."""
    run.quiet()
    n.optimize.optimize_with_rolling_horizon(horizon=horizon, overlap=overlap, solver_name=run.SOLVER,
                                             solver_options={**run.QUIET_SOLVER, "solver": "ipm"}, progress=False,
                                             include_objective_constant=True)
    n.model.solver_model = None
    return n


def cost(n: pypsa.Network) -> float:
    """Dispatch cost summed from the results, so both solves are scored the same way."""
    p = n.generators_t.p
    return float((p * n.generators.marginal_cost).sum().sum() + (n.storage_units_t.p[names.unit("battery")].clip(lower=0) * 0.5).sum())


def battery_stats(n: pypsa.Network) -> dict[str, float]:
    price = n.buses_t.marginal_price["grid"]
    p = n.storage_units_t.p[names.unit("battery")]
    energy = BATTERY["p_nom"] * BATTERY["max_hours"]
    return {
        "revenue_eur": float((price * p).sum()),
        "cycles": float(p.clip(lower=0).sum() / energy),
        "final_soc_mwh": float(n.storage_units_t.state_of_charge[names.unit("battery")].iloc[-1]),
    }


def runs() -> dict[str, pypsa.Network]:
    nets = {"perfect foresight": solve(build())}
    for name, (h, o) in CASES.items():
        nets[name] = solve_rolling(build(), horizon=h, overlap=o)
    return nets


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    c = {k: cost(n) for k, n in nets.items()}
    b = {k: battery_stats(n) for k, n in nets.items()}
    base = c["perfect foresight"]
    return {
        "cost_eur": c,
        "cost_gap_pct": {k: float(100 * (v - base) / base) for k, v in c.items()},
        "battery_revenue_eur": {k: v["revenue_eur"] for k, v in b.items()},
        "battery_cycles": {k: v["cycles"] for k, v in b.items()},
        "final_state_of_charge_mwh": {k: v["final_soc_mwh"] for k, v in b.items()},
        "avg_price_eur_mwh": {k: float(n.buses_t.marginal_price["grid"].mean()) for k, n in nets.items()},
        "peaker_energy_mwh": {k: float(n.generators_t.p[names.gen("OCGT")].sum()) for k, n in nets.items()},
        "cases": {k: {"horizon_h": h, "overlap_h": o} for k, (h, o) in CASES.items()},
        "windows": int(-(-len(nets["perfect foresight"].snapshots) // 24)),
    }


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    soc = pd.DataFrame({k: n.storage_units_t.state_of_charge[names.unit("battery")].round(1) for k, n in nets.items()})
    option, ds = charts.time_series(soc, "MWh")
    soc_fig = bundle.Figure(option, ds, title="Battery state of charge",
                            caption="Perfect foresight carries charge across days for the evenings that pay most; the "
                            "rolling solves, seeing a day at a time, end every window empty and cycle on each day's "
                            "own spread.")
    price = pd.DataFrame({k: n.buses_t.marginal_price["grid"].round(2) for k, n in nets.items()})
    option, ds = charts.time_series(price, "EUR/MWh", step="end")
    price_fig = bundle.Figure(option, ds, title="Hourly price",
                              caption="Where the two prices differ the rolling solve has a different unit at the margin, "
                              "usually because the battery arrived at the evening peak empty or full at the wrong time.")
    b = {k: battery_stats(n) for k, n in nets.items()}
    option, ds = charts.bars(list(nets), {"extra dispatch cost vs foresight": [round((cost(n) - cost(nets["perfect foresight"])) / 1e3, 1) for n in nets.values()],
                                          "battery revenue": [round(b[k]["revenue_eur"] / 1e3, 1) for k in nets]},
                             "kEUR", category_name="approach")
    bars = bundle.Figure(option, ds, title="Fortnight cost and battery revenue",
                         caption="Extra system cost over the perfect-foresight solve, and what the battery earned. "
                         "The overlap does not close the gap here: every window still ends with the battery worth "
                         "nothing, so it is emptied before the window closes whatever the next day looks like.")
    return {"state_of_charge": soc_fig, "price_comparison": price_fig, "cost_and_revenue": bars}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
