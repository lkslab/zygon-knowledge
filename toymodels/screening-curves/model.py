# SPDX-License-Identifier: MIT
"""screening-curves: the textbook generation-mix argument, solved two ways.

Each technology's annual cost per MW is a line in full-load hours: fixed cost plus
marginal cost times hours. The cheapest line at every utilisation, read against the
load duration curve, gives the optimal capacity of each technology. The same numbers
come out of a PyPSA capacity expansion against that load duration curve.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402
from _lib import carrier_style as cs  # noqa: E402

SLUG = "screening-curves"
TITLE = "Screening curves and the optimal thermal mix"

# annualised fixed cost EUR/MW/a, marginal cost EUR/MWh, in merit order
TECH = {
    "nuclear": (250_000, 10),
    "coal": (150_000, 30),
    "CCGT": (80_000, 60),
    "OCGT": (40_000, 120),
}
VOLL = 3000
STEPS = 100
PEAK_MW, BASE_MW = 10_000, 3_000
HOURS = profiles.HOURS_PER_YEAR


def build() -> pypsa.Network:
    levels, weights = profiles.load_duration_synthetic(STEPS, PEAK_MW, BASE_MW)
    n = pypsa.Network()
    n.set_snapshots(pd.Index(levels.index, name="snapshot"))
    n.snapshot_weightings.loc[:, :] = weights.to_numpy()[:, None]
    n.add("Carrier", list(TECH) + ["load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, (capex, mc) in TECH.items():
        n.add("Generator", names.gen(carrier), bus="grid", carrier=carrier, p_nom_extendable=True, capital_cost=capex, marginal_cost=mc)
    n.add("Generator", names.gen("load shedding"), bus="grid", carrier="load shedding", p_nom=1e6, marginal_cost=VOLL)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=levels)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def breakevens() -> dict[str, float]:
    """Full-load hours above which the next-cheaper-to-run technology wins, in merit order.

    Between neighbours i (higher fixed, lower marginal) and j: capex_i + mc_i*h = capex_j + mc_j*h.
    The last boundary is against load shedding at the value of lost load.
    """
    names = list(TECH)
    out: dict[str, float] = {}
    for a, b in zip(names[:-1], names[1:]):
        (ca, ma), (cb, mb) = TECH[a], TECH[b]
        out[f"{a}|{b}"] = (ca - cb) / (mb - ma)
    c_last, m_last = TECH[names[-1]]
    out[f"{names[-1]}|load shedding"] = c_last / (VOLL - m_last)
    return out


def analytic_capacities() -> dict[str, float]:
    """Read the load duration curve at each breakeven.

    In merit order, a technology serves the band of load between the level exceeded for
    its breakeven hours with the next technology and the level exceeded for the previous
    breakeven; the baseload unit's band starts at zero.
    """
    levels, weights = profiles.load_duration_synthetic(STEPS, PEAK_MW, BASE_MW)
    hours_exceeded = (weights.cumsum() - weights / 2).to_numpy()  # midpoint of each step

    def load_at(h: float) -> float:
        return float(np.interp(h, hours_exceeded, levels.to_numpy(), left=PEAK_MW, right=BASE_MW))

    names = list(TECH)
    be = list(breakevens().values())  # one boundary per technology, in merit order
    result: dict[str, float] = {}
    lower_level = 0.0
    for name, h in zip(names, be):
        upper_level = load_at(h)
        result[name] = max(0.0, upper_level - lower_level)
        lower_level = upper_level
    return result


def numbers(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    cap_opt = names.plain(n.generators.p_nom_opt).reindex(list(TECH))
    analytic = analytic_capacities()
    supply = names.plain(n.generators_t.p).mul(w, axis=0).sum()
    price = n.buses_t.marginal_price["grid"]
    hours_at = price.groupby(price.round(2)).apply(lambda s: float(w[s.index].sum()))
    flh = {t: float(supply[t] / cap_opt[t]) if cap_opt[t] > 1e-3 else None for t in TECH}
    return {
        "breakeven_full_load_hours": {k: float(v) for k, v in breakevens().items()},
        "optimal_capacity_mw": {t: float(cap_opt[t]) for t in TECH},
        "analytic_capacity_mw": {t: float(v) for t, v in analytic.items()},
        "max_abs_deviation_mw": float(max(abs(cap_opt[t] - analytic[t]) for t in TECH)),
        "full_load_hours": flh,
        "lcoe_eur_mwh": {t: float((TECH[t][0] + TECH[t][1] * flh[t]) / flh[t]) if flh[t] else None for t in TECH},
        "hours_at_price": {str(k): v for k, v in hours_at.items()},
        "load_shed_mwh": float(supply["load shedding"]),
        "total_cost_meur_a": float(n.objective / 1e6),
        "avg_price_eur_mwh": float((price * n.loads_t.p_set["demand"] * w).sum() / (n.loads_t.p_set["demand"] * w).sum()),
    }


def screening_intuition(n: pypsa.Network) -> bundle.Figure:
    """The two-panel textbook figure: cost lines over full-load hours above, the load duration
    curve below on the same hours, the breakevens dropped through both, the load bands each
    technology serves filled in its colour."""
    be = {k: v for k, v in breakevens().items() if 100 < v < HOURS}  # the 14 h against lost load would crowd the axis
    curves = [charts.Curve(t, [0.0, HOURS], [c / 1e3, (c + m * HOURS) / 1e3], width=1.5) for t, (c, m) in TECH.items()]
    # the lower envelope is piecewise linear, with a vertex at every breakeven
    grid = sorted({0.0, float(HOURS), *be.values()})
    envelope = [min(c + m * h for c, m in TECH.values()) / 1e3 for h in grid]
    curves.append(charts.Curve("cheapest at that utilisation", grid, envelope, color=cs.NEUTRAL, width=3.5))
    levels, weights = profiles.load_duration_synthetic(STEPS, PEAK_MW, BASE_MW)
    hx: list[float] = []
    hy: list[float] = []
    h0 = 0.0
    for level, w in zip(levels.to_numpy(), weights.to_numpy()):
        hx += [h0, h0 + float(w)]
        hy += [float(level)] * 2
        h0 += float(w)
    curves.append(charts.Curve("load duration curve", hx, hy, color=cs.NEUTRAL, width=2, panel=1))
    areas = []
    lo = 0.0
    caps = names.plain(n.generators.p_nom_opt)
    for tech in TECH:
        hi = lo + float(caps[tech])
        xs = [x for x, y in zip(hx, hy) if y > lo + 1e-6]
        ys = [min(y, hi) for x, y in zip(hx, hy) if y > lo + 1e-6]
        if xs:
            areas.append(charts.Area(tech, xs, [lo] * len(xs), ys, cs.colour(tech) or cs.NEUTRAL, panel=1))
        lo = hi
    option, ds = charts.xy_areas(
        curves, areas,
        x_name="Hours per year a plant runs (top) / the load is exceeded (bottom)",
        units=["kEUR per MW per year", "MW"],
        x_marks=[{"value": round(v), "label": f"{round(v):,} h"} for v in be.values()],
        x_max=float(HOURS),
        y_max=[400.0, None],
    )
    return bundle.Figure(
        option, ds, title="From cost lines to the optimal mix",
        caption="Top: what a MW of each technology costs per year if it runs a given number of hours, building cost "
        "plus running cost; the thick line is the cheapest at each utilisation. Bottom: the load, sorted from the "
        "highest hour; each band of it is served by the technology that is cheapest for the hours that band is present.",
    )


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    h = np.linspace(0, HOURS, 60)
    lines = pd.DataFrame({t: (c + m * h) / 1e3 for t, (c, m) in TECH.items()}, index=pd.Index(h.round(0), name="flh"))
    marks = [{"value": float(v), "label": k.replace("|", " / ")} for k, v in breakevens().items() if v < HOURS]
    option, ds = charts.xy_lines(lines.round(1), "Full-load hours per year", "kEUR/MW/a", marks=marks, x_extra={"min": 0, "max": HOURS})
    sc = bundle.Figure(option, ds, title="Screening curves",
                       caption="Annual cost per MW as a function of utilisation. The lower envelope picks the technology; "
                       "the dashed lines are the breakeven hours where the envelope switches.")
    levels, weights = profiles.load_duration_synthetic(STEPS, PEAK_MW, BASE_MW)
    hours = (weights.cumsum() - weights).round(0)
    ldc = pd.DataFrame({"load": levels.round(0).to_numpy()}, index=pd.Index(hours.to_numpy(), name="hours"))
    be = breakevens()
    cum = 0.0
    caps = names.plain(n.generators.p_nom_opt)
    band_marks = []
    for t in TECH:
        cum += float(caps[t])
        band_marks.append({"value": cum, "label": t})
    option, ds = charts.xy_lines(ldc, "Hours per year the load is exceeded", "MW", step="end", x_extra={"min": 0, "max": HOURS})
    option["series"][0]["areaStyle"] = {"opacity": 0.15}
    option["series"][0]["markLine"] = charts.mark_lines(band_marks, axis="yAxis")
    option["series"][0]["markLine"]["label"]["position"] = "insideEndTop"
    ldc_fig = bundle.Figure(option, ds, title="Load duration curve with the optimal capacity bands",
                            caption="Horizontal lines are the cumulative optimal capacities; each band's technology is the "
                            "cheapest for the hours that band of load is present.")
    analytic = analytic_capacities()
    option, ds = charts.bars(list(TECH), {"optimised": [round(float(caps[t]), 1) for t in TECH], "analytic": [round(analytic[t], 1) for t in TECH]}, "MW", category_name="technology")
    mix = bundle.Figure(option, ds, title="Optimal capacities: PyPSA vs screening-curve arithmetic",
                        caption="The LP and the breakeven arithmetic agree up to the load duration curve's step resolution.")
    return {"screening_intuition": screening_intuition(n), "screening_curves": sc, "load_duration_curve": ldc_fig, "optimal_mix": mix}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
