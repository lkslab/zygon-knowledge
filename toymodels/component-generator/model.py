# SPDX-License-Identifier: MIT
"""component-generator: what a PyPSA Generator is, on the smallest network that shows it.

One bus, one load, two Generators built from the same component: a wind farm whose
availability changes every hour (`p_max_pu` a time series, `marginal_cost` 0) and a gas
plant that is always available but costs 55 EUR/MWh to run. Each Generator is one decision
per hour, bounded by its capacity times its availability, and the optimiser fills the load
with the cheaper one first.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402
from _lib import carrier_style as cs  # noqa: E402

SLUG = "component-generator"
TITLE = "What a Generator is"

WIND_P_NOM = 2000  # MW, more than the night load so the optimiser has to curtail
GAS_P_NOM = 1200  # MW, enough on its own for the peak so nothing is ever unserved
GAS_MARGINAL_COST = 55  # EUR/MWh
BASE_MW, PEAK_MW = 600, 1100


def build(*, wind_p_nom: float = WIND_P_NOM, gas_p_nom: float = GAS_P_NOM, gas_marginal_cost: float = GAS_MARGINAL_COST) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(1))
    n.add("Carrier", ["AC", "onwind", "CCGT", "load"])
    n.add("Bus", "grid", carrier="AC")
    # the same component twice: what differs is only the attribute values
    n.add("Generator", "onwind", bus="grid", carrier="onwind", p_nom=wind_p_nom, marginal_cost=0,
          p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", "CCGT", bus="grid", carrier="CCGT", p_nom=gas_p_nom, marginal_cost=gas_marginal_cost)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def _available(n: pypsa.Network) -> pd.Series:
    """What the wind Generator could give each hour: `p_nom * p_max_pu`."""
    return n.generators.p_nom["onwind"] * n.generators_t.p_max_pu["onwind"]


def numbers(n: pypsa.Network) -> dict[str, float]:
    p = n.generators_t.p
    available = _available(n)
    load = n.loads_t.p_set["demand"]
    return {
        "wind_energy_mwh": float(p["onwind"].sum()),
        "wind_available_mwh": float(available.sum()),
        "wind_curtailed_mwh": float((available - p["onwind"]).clip(lower=0).sum()),
        "gas_energy_mwh": float(p["CCGT"].sum()),
        "hours_gas_runs": int((p["CCGT"] > 1e-3).sum()),
        "total_cost_eur": float(n.objective),
        "peak_load_mw": float(load.max()),
        "wind_p_max_pu_range": [float(n.generators_t.p_max_pu["onwind"].min()), float(n.generators_t.p_max_pu["onwind"].max())],
    }


def generator_schematic(n: pypsa.Network) -> bundle.Figure:
    """The network as a one-line diagram: the busbar, the two Generators hung off it with
    the attributes that define them, the load below."""
    g = n.generators
    pu = n.generators_t.p_max_pu["onwind"]
    load = n.loads_t.p_set["demand"]
    nodes = [
        charts.Node("grid", "bus", 360, 190, label="Bus, carrier AC", label_position="bottom"),
        charts.Node(
            "onwind", "generator", 262, 86, carrier="onwind", label_position="left",
            label=f"bus: grid\np_nom: {g.p_nom['onwind']:.0f} MW\nmarginal_cost: {g.marginal_cost['onwind']:.0f} EUR/MWh"
            f"\np_max_pu: {pu.min():.2f}..{pu.max():.2f} per hour",
        ),
        charts.Node(
            "CCGT", "generator", 458, 86, carrier="CCGT", label_position="right",
            label=f"bus: grid\np_nom: {g.p_nom['CCGT']:.0f} MW\nmarginal_cost: {g.marginal_cost['CCGT']:.0f} EUR/MWh"
            "\np_max_pu: 1 (default)",
        ),
        charts.Node("demand", "load", 360, 262, carrier="load", focus=False, label_position="right",
                    label=f"Load, p_set {load.min():.0f}..{load.max():.0f} MW"),
    ]
    edges = [charts.Edge("onwind", "grid"), charts.Edge("CCGT", "grid"), charts.Edge("grid", "demand")]
    option, ds = charts.network_diagram(nodes, edges, height=300)
    return bundle.Figure(
        option, ds, title="Two Generators on one bus",
        caption="One component, two sets of attribute values: where it sits (bus), how much it can give "
        "(p_nom times p_max_pu, a time series for the wind farm, 1 for the gas plant) and what each MWh "
        "costs (marginal_cost). The load below is what they have to meet.",
    )


def dispatch_within_bounds(n: pypsa.Network) -> bundle.Figure:
    """Each Generator's output against its own upper bound and the load."""
    p = n.generators_t.p
    df = pd.DataFrame({
        "onwind": p["onwind"].round(1),
        "CCGT": p["CCGT"].round(1),
        "wind p_nom x p_max_pu": _available(n).round(1),
        "load": n.loads_t.p_set["demand"].round(1),
    })
    ds = charts.dataset_from_frame(df, "snapshot")
    palette = charts.Palette()
    palette.seen["wind p_nom x p_max_pu"] = cs.NEUTRAL  # a bound, not a flow: neutral grey, dashed
    series = [
        charts.line_series("onwind", "ts", "snapshot", palette, stack="supply", area=True),
        charts.line_series("CCGT", "ts", "snapshot", palette, stack="supply", area=True),
        charts.line_series("wind p_nom x p_max_pu", "ts", "snapshot", palette, dashed=True),
        charts.line_series("load", "ts", "snapshot", palette),
    ]
    option = {
        "dataset": [{"id": "ts"}],
        "tooltip": charts.LINE_TOOLTIP,
        "grid": {**charts.GRID, "left": charts.AXIS_NAME_MARGIN},
        "xAxis": charts.time_axis(),
        "yAxis": charts.value_axis("MW"),
        "legend": {**charts.LEGEND, "data": list(df.columns)},
        "series": series,
    }
    return bundle.Figure(
        option, {"ts": ds}, title="Output stays inside p_nom times p_max_pu",
        caption="Wind output (area) follows its dashed upper bound whenever that is below the load, and "
        "the gas plant fills what is left; when the wind could give more than the load, the surplus is "
        "curtailed, since a Generator's output is a free variable between its bounds.",
    )


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    return {"generator_schematic": generator_schematic(n), "dispatch_within_bounds": dispatch_within_bounds(n)}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
