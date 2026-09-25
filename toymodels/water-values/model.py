# SPDX-License-Identifier: MIT
"""water-values: a hydro reservoir with seasonal inflow, and what a myopic operator
should think a stored MWh is worth.

Solved over a stylised year with perfect foresight, the dual of the reservoir's energy
balance is the marginal value of stored water in every snapshot. A rolling-horizon solve
that ignores it drains the reservoir on the first expensive week; the same rolling solve
with the water value charged as the cost of releasing water behaves almost like the
perfect-foresight one. The pattern of PyPSA's water-value example on a StorageUnit.
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

SLUG = "water-values"
TITLE = "Water values for a seasonal reservoir"

EVERY_H = 12
MEAN_LOAD_MW = 100
HYDRO = dict(p_nom=80, max_hours=600)  # 80 MW turbine, 48 GWh reservoir
INFLOW_MEAN_MW = 45
WIND_MW = 130
CCGT = dict(p_nom=70, marginal_cost=60)
OCGT = dict(p_nom=100, marginal_cost=120)
VOLL = 3000
WINDOW = 28  # snapshots per rolling window: two weeks at 12 h


def inflow(index: pd.DatetimeIndex, *, seed: int = 7) -> pd.Series:
    """Snowmelt-shaped inflow: a spring peak, a dry late summer, noise, mean INFLOW_MEAN_MW."""
    rng = np.random.default_rng(seed)
    doy = index.dayofyear.to_numpy()
    melt = np.exp(-((doy - 130) / 35) ** 2) * 2.2
    base = 0.4 + 0.3 * np.cos(2 * np.pi * (doy - 300) / 365.25)
    shape = np.clip(base + melt, 0.05, None) * (1 + 0.15 * rng.standard_normal(len(index)))
    shape = np.clip(shape, 0.02, None)
    return pd.Series(shape / shape.mean() * INFLOW_MEAN_MW, index=index, name="inflow")


def build() -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.year_index(EVERY_H))
    n.snapshot_weightings.loc[:, :] = EVERY_H
    n.add("Carrier", ["AC", "hydro", "onwind", "CCGT", "OCGT", "load shedding"])
    n.add("Bus", "grid", carrier="AC")
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.annual_load(n.snapshots, MEAN_LOAD_MW))
    n.add("Generator", "onwind", bus="grid", carrier="onwind", p_nom=WIND_MW, p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", "CCGT", bus="grid", carrier="CCGT", **CCGT)
    n.add("Generator", "OCGT", bus="grid", carrier="OCGT", **OCGT)
    n.add("Generator", "load shedding", bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=VOLL)
    n.add("StorageUnit", "hydro", bus="grid", carrier="hydro", inflow=inflow(n.snapshots), cyclic_state_of_charge=False,
          state_of_charge_initial=HYDRO["p_nom"] * HYDRO["max_hours"] * 0.5, spill_cost=0.0, p_min_pu=0, **HYDRO)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n, assign_all_duals=True)


def solve_rolling(n: pypsa.Network) -> pypsa.Network:
    run.quiet()
    n.optimize.optimize_with_rolling_horizon(horizon=WINDOW, overlap=0, solver_name=run.SOLVER,
                                             solver_options={**run.QUIET_SOLVER, "solver": "ipm"}, progress=False,
                                             include_objective_constant=True)
    n.model.solver_model = None
    return n


def water_value(n: pypsa.Network) -> pd.Series:
    """Marginal value of a stored MWh: the dual of the reservoir's energy balance.

    `n.storage_units_t.mu_energy_balance` is filled when `assign_all_duals=True` and is
    already in EUR per MWh of stored energy (PyPSA scales the constraint by the
    snapshot weighting). Its sign follows the constraint's orientation, so the absolute
    value is taken; it lies between zero (spill looming) and the dearest fuel.
    """
    return n.storage_units_t.mu_energy_balance["hydro"].abs()


def cost(n: pypsa.Network) -> float:
    w = n.snapshot_weightings.generators
    p = n.generators_t.p
    return float((p.mul(w, axis=0) * n.generators.marginal_cost).sum().sum())


def runs() -> tuple[dict[str, pypsa.Network], pd.Series]:
    pf = solve(build())
    wv = water_value(pf)
    naive = solve_rolling(build())
    informed = build()
    # the water value enters twice: releasing a MWh costs it (so hydro only runs when the
    # price is above it) and spilling a MWh costs it too (so inflow is stored, not wasted)
    informed.storage_units_t.marginal_cost["hydro"] = wv.to_numpy()
    informed.storage_units.loc["hydro", "spill_cost"] = float(wv.mean())
    solve_rolling(informed)
    return {"perfect foresight": pf, "rolling horizon": naive, "rolling + water value": informed}, wv


def summary(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    return {
        "cost_meur_a": cost(n) / 1e6,
        "spill_gwh": float((n.storage_units_t.spill["hydro"] * w).sum() / 1e3) if "spill" in n.storage_units_t else 0.0,
        "shortage_hours": float(w[n.generators_t.p["load shedding"] > 1e-3].sum()),
        "hydro_gwh": float((n.storage_units_t.p["hydro"] * w).sum() / 1e3),
        "min_reservoir_gwh": float(n.storage_units_t.state_of_charge["hydro"].min() / 1e3),
        "end_reservoir_gwh": float(n.storage_units_t.state_of_charge["hydro"].iloc[-1] / 1e3),
    }


def numbers(nets: dict[str, pypsa.Network], wv: pd.Series) -> dict:
    base = cost(nets["perfect foresight"])
    out = {name: summary(n) for name, n in nets.items()}
    out["cost_gap_pct"] = {name: float(100 * (cost(n) - base) / base) for name, n in nets.items()}
    price = nets["perfect foresight"].buses_t.marginal_price["grid"]
    out["water_value_eur_mwh"] = {"mean": float(wv.mean()), "min": float(wv.min()), "max": float(wv.max()),
                                  "spring_min_month": str(wv.groupby(wv.index.month).mean().idxmin())}
    out["mean_price_perfect_eur_mwh"] = float(price.mean())
    out["reservoir_energy_gwh"] = HYDRO["p_nom"] * HYDRO["max_hours"] / 1e3
    out["inflow_gwh_a"] = float(inflow(nets["perfect foresight"].snapshots).sum() * EVERY_H / 1e3)
    return out


def figures(nets: dict[str, pypsa.Network], wv: pd.Series) -> dict[str, bundle.Figure]:
    soc = pd.DataFrame({k: (n.storage_units_t.state_of_charge["hydro"] / 1e3).round(2) for k, n in nets.items()})
    option, ds = charts.time_series(soc, "GWh", slider=False)
    soc_fig = bundle.Figure(option, ds, title="Reservoir level over the year",
                            caption="Perfect foresight keeps water for the winter; the naive rolling solve spends it "
                            "as soon as gas is on the margin and runs dry before the melt. Charging the water value "
                            "as the cost of releasing brings the rolling solve close to the foresight path.")
    pf = nets["perfect foresight"]
    wvdf = pd.DataFrame({"water value": wv.round(2), "price": pf.buses_t.marginal_price["grid"].round(2)})
    option, ds = charts.time_series(wvdf, "EUR/MWh", slider=False)
    option["yAxis"]["max"] = 200
    wv_fig = bundle.Figure(option, ds, title="Water value against the price (perfect foresight)",
                           caption="The dual of the reservoir balance: what one more stored MWh would save. It sits "
                           "near the gas cost most of the year, falls toward zero when spill looms in spring and "
                           "rises when the reservoir is the marginal source. Axis clipped at 200 EUR/MWh.")
    labels = list(nets)
    s = {k: summary(n) for k, n in nets.items()}
    option, ds = charts.bars(labels, {"dispatch cost": [round(s[k]["cost_meur_a"], 3) for k in labels]}, "MEUR/a", category_name="approach")
    cost_fig = bundle.Figure(option, ds, title="Annual dispatch cost by approach",
                             caption="What a year costs with perfect foresight, with a week-ahead rolling solve, and "
                             "with that rolling solve given the water value as the cost of releasing water.")
    return {"reservoir_level": soc_fig, "water_value": wv_fig, "cost_comparison": cost_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets, wv = runs()
    nums = numbers(nets, wv)
    figs = figures(nets, wv)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
