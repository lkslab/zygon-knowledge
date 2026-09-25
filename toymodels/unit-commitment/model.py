# SPDX-License-Identifier: MIT
"""unit-commitment: two committable thermal units with start-up costs and minimum
up/down times against a two-day load, plus a peaker that is never committed.

The integer problem decides when to switch units on; a second solve with the
commitment fixed recovers prices (an integer program has no duals), and a linearised
commitment shows how the relaxation prices the same day.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "unit-commitment"
TITLE = "Unit commitment and its prices"

# carrier: capacity MW, marginal cost, p_min_pu, start-up cost EUR, min up h, min down h
UNITS = {
    "coal": dict(p_nom=1000, marginal_cost=30, p_min_pu=0.4, start_up_cost=5000, min_up_time=4, min_down_time=4),
    "CCGT": dict(p_nom=800, marginal_cost=60, p_min_pu=0.3, start_up_cost=1500, min_up_time=2, min_down_time=2),
}
PEAKER = dict(p_nom=500, marginal_cost=120)
BASE_MW, PEAK_MW = 700, 1600


def build(*, base_mw: float = BASE_MW, peak_mw: float = PEAK_MW) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(2))
    n.add("Carrier", list(UNITS) + ["OCGT", "load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, attrs in UNITS.items():
        n.add("Generator", carrier, bus="grid", carrier=carrier, committable=True, **attrs)
    n.add("Generator", "OCGT", bus="grid", carrier="OCGT", **PEAKER)
    n.add("Generator", "load shedding", bus="grid", carrier="load shedding", p_nom=1e4, marginal_cost=3000)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, base_mw, peak_mw))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n, solver_options={"mip_rel_gap": 1e-6})


def fixed_status_lp(n: pypsa.Network) -> pypsa.Network:
    """The LP with the MILP's commitment frozen: its duals are the dispatch prices."""
    m = n.copy()
    status = n.generators_t.status
    for unit in UNITS:
        m.generators.loc[unit, "committable"] = False
        m.generators_t.p_max_pu[unit] = status[unit].astype(float)
        m.generators_t.p_min_pu[unit] = status[unit].astype(float) * n.generators.loc[unit, "p_min_pu"]
    m.generators.loc[list(UNITS), "p_min_pu"] = 0.0
    run.solve(m)
    return m


def linearised(n: pypsa.Network) -> pypsa.Network:
    m = build()
    run.solve(m, linearized_unit_commitment=True)
    return m


def numbers(n: pypsa.Network) -> dict:
    fixed = fixed_status_lp(n)
    relaxed = linearised(n)
    status = n.generators_t.status[list(UNITS)]
    starts = (status.diff().fillna(0) > 0).sum()
    load = n.loads_t.p_set["demand"]
    p_fixed = fixed.buses_t.marginal_price["grid"]
    p_relaxed = relaxed.buses_t.marginal_price["grid"]
    su_cost = sum(int(starts[u]) * UNITS[u]["start_up_cost"] for u in UNITS)
    at_min = {u: int(((n.generators_t.p[u] - UNITS[u]["p_nom"] * UNITS[u]["p_min_pu"]).abs() < 1e-3).sum()) for u in UNITS}
    return {
        "total_cost_uc_eur": float(n.objective),
        "total_cost_linearised_eur": float(relaxed.objective),
        "integrality_gap_pct": float(100 * (n.objective - relaxed.objective) / relaxed.objective),
        "start_ups": {u: int(starts[u]) for u in UNITS},
        "start_up_cost_share_pct": float(100 * su_cost / n.objective),
        "hours_at_min_load": at_min,
        "hours_committed": {u: int(status[u].sum()) for u in UNITS},
        "avg_price_fixed_status_eur_mwh": float((p_fixed * load).sum() / load.sum()),
        "avg_price_linearised_eur_mwh": float((p_relaxed * load).sum() / load.sum()),
        "min_price_linearised_eur_mwh": float(p_relaxed.min()),
        "peaker_energy_mwh": float(n.generators_t.p["OCGT"].sum()),
    }


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    fixed = fixed_status_lp(n)
    relaxed = linearised(n)
    status = n.generators_t.status[list(UNITS)].astype(int)
    option, ds = charts.status_steps(status)
    status_fig = bundle.Figure(option, ds, title="Commitment status", height=240,
                               caption="Each band is one unit: raised while committed. Minimum up and down times keep the "
                               "cheap coal unit on through the night trough rather than cycling it.")
    stack = n.generators_t.p[list(UNITS) + ["OCGT"]].round(1)
    option, ds = charts.time_series(stack, "MW", stack=True, area=True)
    dispatch = bundle.Figure(option, ds, title="Dispatch", caption="Committed units run at least at their minimum part load; the peaker fills the evening.")
    prices = pd.DataFrame({
        "fixed commitment": fixed.buses_t.marginal_price["grid"].round(2),
        "linearised commitment": relaxed.buses_t.marginal_price["grid"].round(2),
    })
    option, ds = charts.time_series(prices, "EUR/MWh", step="end")
    price_fig = bundle.Figure(option, ds, title="Prices: fixed vs linearised commitment",
                              caption="With commitment frozen the price is the marginal cost of the flexible unit, and can "
                              "sit below every marginal cost when a unit is forced to its minimum. The linearised "
                              "problem prices start-up costs into the hours that trigger them.")
    return {"unit_status": status_fig, "dispatch_stack": dispatch, "price_uc_vs_relaxed": price_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
