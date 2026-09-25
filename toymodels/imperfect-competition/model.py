# SPDX-License-Identifier: MIT
"""imperfect-competition: two strategic generators facing a linear demand curve.

Perfect competition is a PyPSA welfare maximisation (a quadratic programme, the demand
curve entering as a sink with a quadratic marginal cost). The Cournot-Nash equilibrium
is solved in closed form and confirmed by iterated best responses, each a small linopy
quadratic programme; a single-firm monopoly closes the range. Withheld quantity,
markup and deadweight loss follow.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import linopy
import numpy as np
import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, run  # noqa: E402

SLUG = "imperfect-competition"
TITLE = "Cournot competition against a linear demand curve"

A, B = 200.0, 0.1  # inverse demand P = A - B * Q (EUR/MWh, Q in MW)
FIRMS = {"firm 1": 20.0, "firm 2": 40.0}  # constant marginal cost EUR/MWh
CAPACITY = 2000.0  # MW each, never binding


def build() -> pypsa.Network:
    """The competitive market: firms as generators, the demand curve as a price-taking sink.

    Utility of consumption Q is A*Q - B/2 * Q^2; a generator with sign -1, marginal cost -A
    and quadratic marginal cost B/2 puts exactly that into the objective, so minimising
    cost minus utility maximises welfare.
    """
    n = pypsa.Network()
    n.set_snapshots([0])
    n.add("Carrier", ["AC", "load"] + list(FIRMS))
    n.add("Bus", "market", carrier="AC")
    for name, mc in FIRMS.items():
        n.add("Generator", name, bus="market", carrier=name, p_nom=CAPACITY, marginal_cost=mc)
    n.add("Generator", "demand", bus="market", carrier="load", sign=-1, p_nom=A / B, marginal_cost=-A, marginal_cost_quadratic=B / 2)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    # a quadratic objective: let HiGHS pick its QP solver rather than the LP interior point
    return run.solve(n, solver_options={"solver": "choose"})


def best_response(own_cost: float, other_q: float) -> float:
    """max_q (A - B (q + other)) q - c q, solved as a linopy QP (HiGHS)."""
    m = linopy.Model()
    q = m.add_variables(lower=0, upper=CAPACITY, name="q")
    m.add_objective(B * q * q + (own_cost - A + B * other_q) * q)
    m.solve(solver_name="highs", output_flag=False, log_to_console=False, progress=False)
    return float(q.solution)


def cournot_iterated(iterations: int = 30) -> tuple[dict[str, float], list[dict[str, float]]]:
    names = list(FIRMS)
    q = {name: 0.0 for name in names}
    path = [dict(q)]
    for _ in range(iterations):
        for name in names:
            other = sum(v for k, v in q.items() if k != name)
            q[name] = best_response(FIRMS[name], other)
        path.append(dict(q))
    return q, path


def cournot_analytic() -> dict[str, float]:
    (n1, c1), (n2, c2) = FIRMS.items()
    return {n1: max(0.0, (A - 2 * c1 + c2) / (3 * B)), n2: max(0.0, (A - 2 * c2 + c1) / (3 * B))}


def monopoly() -> dict[str, float]:
    name, c = min(FIRMS.items(), key=lambda kv: kv[1])
    return {name: (A - c) / (2 * B), **{k: 0.0 for k in FIRMS if k != name}}


def price(q: dict[str, float]) -> float:
    return A - B * sum(q.values())


def surplus(q: dict[str, float]) -> dict[str, float]:
    Q = sum(q.values())
    P = price(q)
    consumer = 0.5 * (A - P) * Q
    producer = sum((P - FIRMS[k]) * v for k, v in q.items())
    return {"consumer surplus": consumer, "producer surplus": producer, "welfare": consumer + producer}


def regimes(n: pypsa.Network) -> dict[str, dict[str, float]]:
    comp = {k: float(n.generators_t.p.iloc[0][k]) for k in FIRMS}
    nash, _ = cournot_iterated()
    return {"competitive": comp, "cournot": nash, "monopoly": monopoly()}


def numbers(n: pypsa.Network) -> dict:
    reg = regimes(n)
    comp_w = surplus(reg["competitive"])["welfare"]
    out: dict = {"demand_curve": {"intercept_eur_mwh": A, "slope_eur_mwh_per_mw": B}, "marginal_cost_eur_mwh": FIRMS}
    for name, q in reg.items():
        P = price(q)
        s = surplus(q)
        mc_marg = max(FIRMS[k] for k, v in q.items() if v > 1e-6)
        out[name] = {
            "quantity_mw": {k: float(v) for k, v in q.items()},
            "total_quantity_mw": float(sum(q.values())),
            "price_eur_mwh": float(P),
            "markup_over_marginal_cost_eur_mwh": float(P - mc_marg),
            "lerner_index": float((P - mc_marg) / P),
            "consumer_surplus_keur_h": s["consumer surplus"] / 1e3,
            "producer_surplus_keur_h": s["producer surplus"] / 1e3,
            "deadweight_loss_keur_h": (comp_w - s["welfare"]) / 1e3,
        }
    out["quantity_withheld_mw"] = {name: out["competitive"]["total_quantity_mw"] - out[name]["total_quantity_mw"] for name in ("cournot", "monopoly")}
    out["competitive_price_pypsa_dual_eur_mwh"] = float(n.buses_t.marginal_price.iloc[0]["market"])
    out["cournot_analytic_mw"] = cournot_analytic()
    return out


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    reg = regimes(n)
    labels = list(reg)
    option, ds = charts.bars(labels, {k: [round(reg[r][k], 1) for r in labels] for k in FIRMS}, "MW", stack=True, horizontal=False, category_name="regime")
    qty = bundle.Figure(option, ds, title="Quantity supplied by regime",
                        caption="Strategic firms withhold output to lift the price; the monopolist withholds most, and "
                        "the higher-cost firm disappears entirely.")
    grid = np.linspace(0, (A - min(FIRMS.values())) / B, 40)
    (n1, c1), (n2, c2) = FIRMS.items()
    br = pd.DataFrame({
        "best response of firm 1": [max(0.0, (A - c1 - B * q2) / (2 * B)) for q2 in grid],  # q1 as a function of q2, plotted transposed
    }, index=pd.Index(grid.round(1), name="q"))
    br2 = pd.DataFrame({"best response of firm 2": [max(0.0, (A - c2 - B * q1) / (2 * B)) for q1 in grid]}, index=pd.Index(grid.round(1), name="q"))
    # x axis: q1; firm 2's response is q2(q1); firm 1's response is q1(q2), drawn by swapping axes
    rows1 = [[float(q1), None, float(q2)] for q2, q1 in zip(grid, br["best response of firm 1"])]
    rows2 = [[float(q1), float(q2), None] for q1, q2 in zip(grid, br2["best response of firm 2"])]
    rows = sorted(rows1 + rows2, key=lambda r: r[0])
    datasets = {"br": charts.dataset(["q1", "best response of firm 2", "best response of firm 1"], rows)}
    palette = charts.Palette()
    series = [
        {**charts.line_series("best response of firm 2", "br", "q1", palette), "connectNulls": True},
        {**charts.line_series("best response of firm 1", "br", "q1", palette), "connectNulls": True},
    ]
    nash = reg["cournot"]
    series.append({"type": "scatter", "name": "Cournot equilibrium", "data": [[nash[n1], nash[n2]]], "symbolSize": 12,
                   **palette.style("Cournot equilibrium", line=False)})
    option = {
        "dataset": [{"id": "br"}],
        "tooltip": charts.LINE_TOOLTIP,
        "grid": {**charts.GRID, "left": charts.AXIS_NAME_MARGIN, "bottom": 24},
        "xAxis": charts.x_value_axis("Output of firm 1 (MW)", min=0),
        "yAxis": charts.value_axis("Output of firm 2 (MW)", min=0),
        "series": series,
        "legend": {**charts.LEGEND, "data": [s["name"] for s in series]},
    }
    brf = bundle.Figure(option, datasets, title="Best-response functions",
                        caption="Each firm's profit-maximising output given the other's. The lines cross at the "
                        "Nash equilibrium, which the iterated best responses converge to.")
    comp_w = surplus(reg["competitive"])["welfare"]
    parts = {"consumer surplus": [], "producer surplus": [], "deadweight loss": []}
    for r in labels:
        s = surplus(reg[r])
        parts["consumer surplus"].append(round(s["consumer surplus"] / 1e3, 2))
        parts["producer surplus"].append(round(s["producer surplus"] / 1e3, 2))
        parts["deadweight loss"].append(round((comp_w - s["welfare"]) / 1e3, 2))
    option, ds = charts.bars(labels, parts, "kEUR/h", stack=True, horizontal=False, category_name="regime")
    wf = bundle.Figure(option, ds, title="Welfare by regime",
                       caption="The stacks sum to the competitive welfare. Market power moves surplus from consumers "
                       "to producers and destroys the deadweight-loss slice outright.")
    return {"quantity_by_regime": qty, "best_responses": brf, "welfare_by_regime": wf}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
