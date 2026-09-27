# SPDX-License-Identifier: MIT
"""security-constrained-lopf: the three-bus triangle dispatched so that no single
line outage overloads the survivors.

A plain optimal power flow uses every line to its rating; if one line then trips, the
loop pushes its flow onto the others and can overload them. The security-constrained
solve adds, for every outage, the post-contingency flows as constraints, and holds
spare capacity on the lines at a cost. Both dispatches are re-checked with a linear
power flow under each outage to show what N-1 buys.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, geography, run  # noqa: E402

SLUG = "security-constrained-lopf"
TITLE = "Security-constrained optimal power flow (N-1)"

TRIANGLE = run.load_model("nodal-prices-lopf")
LOAD_LEVEL = 1.2
LINES = list(TRIANGLE.LINES)
BUSES = TRIANGLE.BUSES


def build() -> pypsa.Network:
    """One snapshot at LOAD_LEVEL of the triangle's base loads; A-B rated 400 MW, the others 1000 MW."""
    return TRIANGLE.build(load_levels=[LOAD_LEVEL])


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def solve_secure(n: pypsa.Network) -> pypsa.Network:
    """`optimize_security_constrained`: every line as a branch outage, post-contingency
    flows from the line outage distribution factors added as constraints."""
    run.quiet()
    status, cond = n.optimize.optimize_security_constrained(branch_outages=n.lines.index, solver_name=run.SOLVER,
                                                            solver_options={**run.QUIET_SOLVER, "solver": "ipm"}, progress=False)
    if (status, cond) != ("ok", "optimal"):
        raise RuntimeError(f"sclopf ended {status}/{cond}")
    n.model.solver_model = None
    return n


def contingency_loading(n: pypsa.Network) -> pd.DataFrame:
    """Post-contingency line loading (% of rating) for a fixed dispatch: rows are the
    outaged line, columns the surviving lines, from a linear power flow with the
    optimised generator outputs held as set points."""
    sn = n.snapshots[0]
    out = {}
    for outage in LINES:
        m = n.copy()
        m.generators_t.p_set = n.generators_t.p.copy()
        m.remove("Line", outage)
        m.lpf(snapshots=[sn])
        loading = 100 * m.lines_t.p0.loc[sn].abs() / m.lines.s_nom
        out[outage] = loading.reindex(LINES)
    return pd.DataFrame(out).T  # outage x line, NaN on the diagonal


def runs() -> dict[str, pypsa.Network]:
    return {"plain": solve(build()), "N-1 secure": solve_secure(build())}


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    plain, secure = nets["plain"], nets["N-1 secure"]
    sn = plain.snapshots[0]
    load_plain, load_secure = contingency_loading(plain), contingency_loading(secure)
    base_plain = 100 * plain.lines_t.p0.loc[sn].abs() / plain.lines.s_nom
    base_secure = 100 * secure.lines_t.p0.loc[sn].abs() / secure.lines.s_nom
    return {
        "cost_plain_eur_h": float(plain.objective),
        "cost_secure_eur_h": float(secure.objective),
        "cost_of_security_pct": float(100 * (secure.objective - plain.objective) / plain.objective),
        "worst_post_contingency_loading_pct": {"plain": float(load_plain.max().max()), "N-1 secure": float(load_secure.max().max())},
        "worst_case": {"plain": f"{load_plain.stack().idxmax()[0]} out, {load_plain.stack().idxmax()[1]} at {load_plain.max().max():.0f} %",
                       "N-1 secure": f"{load_secure.stack().idxmax()[0]} out, {load_secure.stack().idxmax()[1]} at {load_secure.max().max():.0f} %"},
        "base_case_loading_pct": {"plain": {k: float(v) for k, v in base_plain.items()}, "N-1 secure": {k: float(v) for k, v in base_secure.items()}},
        "spare_capacity_held_mw": {k: float(plain.lines.s_nom[k] * (base_plain[k] - base_secure[k]) / 100) for k in LINES},
        "nodal_prices_eur_mwh": {"plain": {b: float(plain.buses_t.marginal_price.loc[sn, b]) for b in BUSES},
                                 "N-1 secure": {b: float(secure.buses_t.marginal_price.loc[sn, b]) for b in BUSES}},
        "dispatch_mw": {"plain": {g: float(plain.generators_t.p.loc[sn, g]) for g in plain.generators.index if not g.startswith("shed")},
                        "N-1 secure": {g: float(secure.generators_t.p.loc[sn, g]) for g in secure.generators.index if not g.startswith("shed")}},
        "load_level": LOAD_LEVEL,
    }


def _loading_bars(df: pd.DataFrame, title: str, caption: str) -> bundle.Figure:
    cats = [f"{o} out" for o in df.index]
    data = {line: [None if pd.isna(v) else round(float(v), 1) for v in df[line]] for line in LINES}
    option, ds = charts.bars(cats, data, "% of rating", category_name="outage")
    option["series"][0]["markLine"] = charts.mark_lines([{"value": 100, "label": "rating"}], axis="yAxis")
    return bundle.Figure(option, ds, title=title, caption=caption)


def outage_flows(n: pypsa.Network, outage: str) -> pd.Series:
    """Flows (MW, signed bus0 -> bus1) on the surviving lines once `outage` trips, with
    the dispatch held: what physics does in the instant before anyone can react."""
    sn = n.snapshots[0]
    m = n.copy()
    m.generators_t.p_set = n.generators_t.p.copy()
    m.remove("Line", outage)
    m.lpf(snapshots=[sn])
    return m.lines_t.p0.loc[sn]


def contingency_map(nets: dict[str, pypsa.Network]) -> bundle.Figure:
    """The plain dispatch in the moment after its worst single outage, on the triangle's
    made-up country: the tripped line dashed, its flow pushed onto the small line."""
    plain = nets["plain"]
    sn = plain.snapshots[0]
    loading = contingency_loading(plain)
    outage, worst = loading.stack().idxmax()
    flows = outage_flows(plain, outage)
    before = plain.lines_t.p0.loc[sn]
    outline, rings = geography.country(TRIANGLE.OUTLINE, TRIANGLE.CUTS, TRIANGLE.BUS_XY)
    load = plain.loads_t.p_set.loc[sn]
    made = plain.generators_t.p.loc[sn].groupby(plain.generators.bus).sum()
    regions, sites = [], []
    for bus, (name, kind, label_at) in TRIANGLE.REGIONS.items():
        use = float(load[f"load {bus}"])
        regions.append(charts.Region(name=name, polygon=rings[bus], value=round((float(made.get(bus, 0.0)) - use) / 1e3, 3),
                                     label_at=label_at, label=f"{kind}\nmakes {made.get(bus, 0.0):.0f} · uses {use:.0f} MW"))
        carrier, p_nom, mc = TRIANGLE.GENS[bus]
        sites.append(charts.Site(name=f"{carrier} {bus}", x=TRIANGLE.BUS_XY[bus][0], y=TRIANGLE.BUS_XY[bus][1], size=p_nom,
                                 carrier=carrier, label=f"{carrier}, {mc} EUR/MWh",
                                 label_position="right" if bus != "B" else "left"))
    links = []
    for name, (b0, b1, _) in TRIANGLE.LINES.items():
        s_nom = float(plain.lines.s_nom[name])
        xy0, xy1 = TRIANGLE.BUS_XY[b0], TRIANGLE.BUS_XY[b1]
        at = TRIANGLE.LINK_LABEL_AT[name]
        if name == outage:
            links.append(charts.Link(name=name, start=xy0, end=xy1, capacity=s_nom, outage=True, label_at=at,
                                     label=f"{name} trips\n(was {abs(before[name]):,.0f} MW)"))
            continue
        f = float(flows[name])
        label = f"{name}: {abs(f):,.0f} MW\non a {s_nom:,.0f} MW line" if abs(f) > s_nom else f"{name}: {abs(f):,.0f} of {s_nom:,.0f} MW"
        links.append(charts.Link(name=name, start=xy0, end=xy1, capacity=s_nom, flow=round(f, 1), label=label, label_at=at))
    option, ds = charts.region_map(regions, outline=outline, sites=sites, links=links,
                                   value_name="net position", unit="GW", low_label="short of power",
                                   high_label="power to spare")
    return bundle.Figure(
        option, ds, title="One line trips: its flow lands on the others",
        caption=f"The plain dispatch at peak load, the moment {outage} trips. Nobody can react that fast: the "
        f"{abs(before[outage]):,.0f} MW it carried reroutes by physics onto the survivors, and {worst} runs at "
        f"{loading.loc[outage, worst]:.0f} % of its rating, so it would trip next.",
    )


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    plain, secure = nets["plain"], nets["N-1 secure"]
    sn = plain.snapshots[0]
    lp = _loading_bars(contingency_loading(plain), "Post-contingency loading, plain dispatch",
                       "Loading of the surviving lines after each single outage, with the plain dispatch held. "
                       "Bars above the rating line are overloads the plain solve never saw.")
    ls = _loading_bars(contingency_loading(secure), "Post-contingency loading, N-1 secure dispatch",
                       "The same check for the secure dispatch: every outage leaves every survivor at or under its rating.")
    prices = {k: [round(float(n.buses_t.marginal_price.loc[sn, b]), 2) for b in BUSES] for k, n in nets.items()}
    option, ds = charts.bars(BUSES, prices, "EUR/MWh", category_name="bus")
    pr = bundle.Figure(option, ds, title="Nodal prices, plain vs N-1",
                       caption="Holding spare line capacity means less cheap import at the constrained buses, so "
                       "their prices rise; the system pays the difference as the cost of security.")
    option, ds = charts.bars(list(nets), {"dispatch cost": [round(float(plain.objective)), round(float(secure.objective))]}, "EUR/h", category_name="dispatch")
    cost = bundle.Figure(option, ds, title="Dispatch cost per hour", caption="The premium for a dispatch that survives any single line outage.")
    return {"contingency_map": contingency_map(nets), "post_contingency_plain": lp, "post_contingency_secure": ls, "nodal_prices": pr, "cost_comparison": cost}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
