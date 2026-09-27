# SPDX-License-Identifier: MIT
"""tracing-infeasibilities: a network that cannot be solved, and how to find out why.

One bus, three days, two thermal units with ramp limits and minimum outputs, no load
shedding, and a load spike that is both too high and too fast. The solve reports
"infeasible" and nothing else. HiGHS can compute an irreducible infeasible subset
(IIS): the smallest set of constraints and bounds that cannot hold together, read
here back into PyPSA's constraint names and snapshots. Adding load shedding repairs
the problem and the price then points at the same hours.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "tracing-infeasibilities"
TITLE = "Tracing an infeasible dispatch problem"

UNITS = {
    "coal": dict(p_nom=1000, marginal_cost=30, p_min_pu=0.3, ramp_limit_up=0.10, ramp_limit_down=0.10),
    "CCGT": dict(p_nom=500, marginal_cost=60, p_min_pu=0.2, ramp_limit_up=0.30, ramp_limit_down=0.30),
}
BASE_MW, PEAK_MW = 700, 1300
SPIKE = {"start": "2025-01-02 18:00", "hours": 2, "mw": 1900}  # above the 1500 MW fleet, after a fast ramp
VOLL = 3000


def build(*, with_shedding: bool = False, spike_mw: float | None = None) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(3))
    n.add("Carrier", list(UNITS) + ["load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, attrs in UNITS.items():
        n.add("Generator", carrier, bus="grid", carrier=carrier, **attrs)
    load = profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW)
    start = pd.Timestamp(SPIKE["start"])
    idx = (n.snapshots >= start) & (n.snapshots < start + pd.Timedelta(hours=SPIKE["hours"]))
    load[idx] = spike_mw if spike_mw is not None else SPIKE["mw"]
    n.add("Load", "demand", bus="grid", carrier="load", p_set=load)
    if with_shedding:
        n.add("Generator", "load shedding", bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=VOLL)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def _label_maps(model) -> tuple[dict[int, tuple[str, tuple]], dict[int, tuple[str, tuple]]]:
    """linopy label -> (name, coordinates) for constraints and variables.

    linopy writes constraint row `c<label>` and variable column `x<label>` to the solver;
    HiGHS reports the IIS by those names, so the labels are the bridge back to PyPSA.
    """
    def collect(container) -> dict[int, tuple[str, tuple]]:
        out: dict[int, tuple[str, tuple]] = {}
        for name in container:
            labels = container[name].labels
            stacked = labels.stack(all=labels.dims) if labels.dims else labels
            for coord, value in zip(stacked.coords["all"].values if labels.dims else [()], stacked.values.ravel()):
                if int(value) >= 0:
                    out[int(value)] = (name, tuple(coord) if isinstance(coord, tuple) else (coord,))
        return out
    return collect(model.constraints), collect(model.variables)


def iis(n: pypsa.Network) -> dict:
    """Solve the model and, if infeasible, compute HiGHS' irreducible infeasible subset."""
    run.quiet()
    n.optimize.create_model()
    status, condition = n.model.solve(solver_name="highs", output_flag=False, log_to_console=False, progress=False)
    if condition != "infeasible":
        return {"condition": condition, "constraints": [], "variables": []}
    h = n.model.solver_model
    h.setOptionValue("presolve", "off")
    h.setOptionValue("iis_strategy", 2)
    h.run()
    _, result = h.getIis()
    cons_map, var_map = _label_maps(n.model)
    rows = []
    for i, bound in zip(result.row_index_, result.row_bound_):
        label = int(re.sub(r"\D", "", h.getRowName(i)[1]))
        name, coord = cons_map.get(label, ("?", ()))
        rows.append({"constraint": name, "coords": [str(c) for c in coord], "bound": int(bound)})
    cols = []
    for i, bound in zip(result.col_index_, result.col_bound_):
        label = int(re.sub(r"\D", "", h.getColName(i)[1]))
        name, coord = var_map.get(label, ("?", ()))
        cols.append({"variable": name, "coords": [str(c) for c in coord], "bound": int(bound)})
    return {"condition": condition, "constraints": rows, "variables": cols}


def numbers(n_infeasible: pypsa.Network, diag: dict, repaired: pypsa.Network) -> dict:
    w = repaired.snapshot_weightings.generators
    shed = repaired.generators_t.p["load shedding"]
    price = repaired.buses_t.marginal_price["grid"]
    by_name = pd.Series([r["constraint"] for r in diag["constraints"]]).value_counts().to_dict() if diag["constraints"] else {}
    hours = sorted({c[0] for r in diag["constraints"] for c in [r["coords"]] if c})
    max_reach = float(sum(u["p_nom"] for u in UNITS.values()))
    load = n_infeasible.loads_t.p_set["demand"]
    return {
        "solver_condition": diag["condition"],
        "iis_size": {"constraints": len(diag["constraints"]), "variable_bounds": len(diag["variables"])},
        "iis_constraints_by_name": by_name,
        "iis_hours": hours,
        "fleet_capacity_mw": max_reach,
        "peak_load_mw": float(load.max()),
        "load_over_capacity_mw": float(load.max() - max_reach),
        "shed_energy_mwh": float((shed * w).sum()),
        "hours_with_shedding": int((shed > 1e-3).sum()),
        "max_price_after_repair_eur_mwh": float(price.max()),
        "hours_at_voll": int((price >= VOLL - 1e-3).sum()),
        "repaired_cost_eur": float(repaired.objective),
    }


def figures(n_infeasible: pypsa.Network, diag: dict, repaired: pypsa.Network) -> dict[str, bundle.Figure]:
    load = n_infeasible.loads_t.p_set["demand"]
    reach = pd.Series(sum(u["p_nom"] for u in UNITS.values()), index=load.index)
    served = (load - repaired.generators_t.p["load shedding"]).round(1)
    df = pd.DataFrame({"load": load.round(1), "fleet capacity": reach, "served after repair": served,
                       "demand no dispatch can meet": (load - served).round(1)})
    option, ds = charts.time_series(df, "MW", step="middle")
    grey = "#6b7280"
    styles = {
        "load": {"lineStyle": {"color": grey, "width": 1.5}, "itemStyle": {"color": grey}},
        "fleet capacity": {"lineStyle": {"color": grey, "width": 1.2, "type": "dashed"}, "itemStyle": {"color": grey}},
        "served after repair": {"lineStyle": {"color": charts.BAND_BELOW, "width": 2.5}, "itemStyle": {"color": charts.BAND_BELOW},
                                "stack": "gap"},
        # stacked on the served load, so its fill is exactly the gap up to the load
        "demand no dispatch can meet": {"lineStyle": {"width": 0, "opacity": 0}, "itemStyle": {"color": charts.BAND_ABOVE},
                                        "areaStyle": {"color": charts.BAND_ABOVE, "opacity": 0.45}, "stack": "gap",
                                        "silent": True},
    }
    for s in option["series"]:
        s.update(styles[s["name"]])
    option["series"] = [option["series"][i] for i in (2, 3, 0, 1)]  # the stack first, the load and capacity lines on top
    spike = bundle.Figure(option, ds, title="The load spike against what the fleet can reach",
                          caption="The spike exceeds the installed capacity and arrives faster than the ramp limits "
                          "allow, so no dispatch satisfies every constraint and the solver can only say infeasible. "
                          "Letting load be shed at a high price makes it solvable: green is what the fleet can "
                          "deliver, vermillion the demand it cannot.")
    counts = pd.Series([r["constraint"] for r in diag["constraints"]]).value_counts() if diag["constraints"] else pd.Series(dtype=int)
    cats = list(counts.index) if len(counts) else ["none"]
    option, ds = charts.bars(cats, {"constraints in the IIS": [int(v) for v in counts.values] or [0]}, "count", horizontal=True, category_name="constraint")
    iis_fig = bundle.Figure(option, ds, title="Constraint families in the irreducible infeasible subset",
                            caption="The smallest set of constraints that cannot hold together, by PyPSA constraint name. "
                            "Nodal balances at the spike hours together with the ramp and capacity limits that "
                            "keep the units from meeting them.")
    price = pd.DataFrame({"price": repaired.buses_t.marginal_price["grid"].round(2)})
    option, ds = charts.time_series(price, "EUR/MWh", step="end")
    price_fig = bundle.Figure(option, ds, title="Price after adding load shedding",
                              caption="With a slack at the value of lost load the problem solves, and the price reaches "
                              "that value exactly in the hours the IIS pointed at, plus the ramp-constrained hours around them.")
    return {"load_vs_reachable": spike, "iis_constraints": iis_fig, "price_after_repair": price_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    broken = build()
    diag = iis(broken)
    repaired = solve(build(with_shedding=True))
    nums = numbers(broken, diag, repaired)
    figs = figures(broken, diag, repaired)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
