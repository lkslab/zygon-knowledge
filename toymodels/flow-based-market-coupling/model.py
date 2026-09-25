# SPDX-License-Identifier: MIT
"""flow-based-market-coupling: three zones in a triangle cleared three ways.

The same generators, loads and lines are cleared as a nodal market (the physics), as
a zonal market with fixed bilateral exchange limits (NTC) and as a flow-based market
whose only constraints on the zones' net positions are the lines' remaining margins
mapped through the power transfer distribution factors (PTDF). The flow-based domain
is a polygon in net-position space; the NTC box sits inside it, and the difference is
exchange the NTC design leaves on the table.
"""

from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, run  # noqa: E402

SLUG = "flow-based-market-coupling"
TITLE = "NTC, flow-based and nodal market coupling"

ZONES = ["A", "B", "C"]
GENS = {"A": ("coal", 400, 20.0), "B": ("CCGT", 400, 60.0), "C": ("OCGT", 400, 120.0)}
LOADS = {"A": 50.0, "B": 200.0, "C": 150.0}
LINES = {"A-B": ("A", "B", 120.0), "B-C": ("B", "C", 120.0), "A-C": ("A", "C", 120.0)}
X_PU = 0.1
RELIABILITY_MARGIN = 0.1  # share of the rating withheld from the market (FRM); RAM = (1 - margin) * rating
NTC_MW = 60.0  # bilateral exchange limit per border under the NTC design
VOLL = 3000.0


def physical() -> pypsa.Network:
    """The real grid: one bus per zone, lines with reactance."""
    n = pypsa.Network()
    n.set_snapshots([0])
    n.add("Carrier", ["AC", "coal", "CCGT", "OCGT", "load shedding"])
    n.add("Bus", ZONES, v_nom=380, carrier="AC")
    for z, (carrier, p_nom, mc) in GENS.items():
        n.add("Generator", f"{carrier} {z}", bus=z, carrier=carrier, p_nom=p_nom, marginal_cost=mc)
        n.add("Generator", f"shed {z}", bus=z, carrier="load shedding", p_nom=1e4, marginal_cost=VOLL)
        n.add("Load", f"load {z}", bus=z, carrier="load", p_set=LOADS[z])
    for name, (b0, b1, s_nom) in LINES.items():
        n.add("Line", name, bus0=b0, bus1=b1, x=X_PU, r=0.01, s_nom=s_nom, carrier="AC")
    return n


def ptdf() -> pd.DataFrame:
    """Line-by-zone PTDF: the flow on each line per MW injected in a zone and withdrawn at
    the slack bus (PyPSA takes the sub-network's first bus, A, so A's column is zero).
    Because the net positions sum to zero the slack choice does not change the flows."""
    n = physical()
    n.determine_network_topology()
    sn = n.sub_networks.obj.iloc[0]
    sn.calculate_PTDF()
    return pd.DataFrame(sn.PTDF, index=list(LINES), columns=list(sn.buses_i()))


def zonal(design: str) -> pypsa.Network:
    """The market: zones tied to a hub by unconstrained links; the design's constraints on
    the net positions (link flows) are added as custom linopy constraints."""
    n = physical()
    n.remove("Line", list(LINES))
    n.add("Bus", "hub", carrier="AC")
    for z in ZONES:
        n.add("Link", f"NP {z}", bus0=z, bus1="hub", carrier="AC", p_nom=1e4, p_min_pu=-1)
    n._design = design  # noqa: SLF001
    return n


def _constrain(n: pypsa.Network, snapshots) -> None:
    m = n.model
    np_ = m.variables["Link-p"]  # net export of each zone into the hub
    if n._design == "NTC":
        for z in ZONES:
            m.add_constraints(np_.sel(name=f"NP {z}") <= 2 * NTC_MW, name=f"ntc-export-{z}")
            m.add_constraints(np_.sel(name=f"NP {z}") >= -2 * NTC_MW, name=f"ntc-import-{z}")
    elif n._design == "flow-based":
        H = ptdf()
        for line in LINES:
            flow = sum(float(H.loc[line, z]) * np_.sel(name=f"NP {z}") for z in ZONES if abs(H.loc[line, z]) > 1e-9)
            ram = (1 - RELIABILITY_MARGIN) * LINES[line][2]
            m.add_constraints(flow <= ram, name=f"fb-upper-{line}")
            m.add_constraints(flow >= -ram, name=f"fb-lower-{line}")


def solve_design(design: str) -> pypsa.Network:
    if design == "nodal":
        return run.solve(physical())
    n = zonal(design)
    return run.solve(n, extra_functionality=_constrain)


def net_positions(n: pypsa.Network) -> pd.Series:
    if "NP A" in n.links.index:
        return pd.Series({z: float(n.links_t.p0.iloc[0][f"NP {z}"]) for z in ZONES})
    gen = n.generators_t.p.iloc[0]
    return pd.Series({z: float(sum(gen[g] for g in n.generators.index if n.generators.bus[g] == z) - LOADS[z]) for z in ZONES})


def domain_polygon() -> np.ndarray:
    """Vertices of the flow-based domain in (NP_A, NP_B); NP_C = -(NP_A + NP_B).

    Every line gives two half-planes |h_A NP_A + h_B NP_B| <= RAM; the feasible region is
    their intersection, found by testing pairwise intersections against all constraints.
    """
    H = ptdf()
    rows = []
    for line in LINES:
        ram = (1 - RELIABILITY_MARGIN) * LINES[line][2]
        # substitute NP_C = -(NP_A + NP_B): the coefficient on each axis is its PTDF minus C's
        a = float(H.loc[line, "A"] - H.loc[line, "C"])
        b = float(H.loc[line, "B"] - H.loc[line, "C"])
        rows += [(a, b, ram), (-a, -b, ram)]
    pts = []
    for (a1, b1, c1), (a2, b2, c2) in itertools.combinations(rows, 2):
        det = a1 * b2 - a2 * b1
        if abs(det) < 1e-9:
            continue
        x = (c1 * b2 - c2 * b1) / det
        y = (a1 * c2 - a2 * c1) / det
        if all(a * x + b * y <= c + 1e-6 for a, b, c in rows):
            pts.append((x, y))
    pts = np.array(sorted(set((round(x, 6), round(y, 6)) for x, y in pts)))
    centre = pts.mean(axis=0)
    order = np.argsort(np.arctan2(pts[:, 1] - centre[1], pts[:, 0] - centre[0]))
    return pts[order]


def _area(poly: np.ndarray) -> float:
    x, y = poly[:, 0], poly[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    cost = {d: float(n.objective) for d, n in nets.items()}
    poly = domain_polygon()
    box = 2 * NTC_MW
    H = ptdf()
    fb = nets["flow-based"]
    np_fb = net_positions(fb)
    flows = {line: float(sum(H.loc[line, z] * np_fb[z] for z in ZONES)) for line in LINES}
    ram = {line: (1 - RELIABILITY_MARGIN) * LINES[line][2] for line in LINES}
    binding = [line for line in LINES if abs(abs(flows[line]) - ram[line]) < 1e-3]
    return {
        "cost_eur_h": cost,
        "welfare_gain_fb_over_ntc_eur_h": cost["NTC"] - cost["flow-based"],
        "cost_of_zonal_vs_nodal_eur_h": {d: cost[d] - cost["nodal"] for d in ("NTC", "flow-based")},
        "net_positions_mw": {d: net_positions(n).round(2).to_dict() for d, n in nets.items()},
        "domain_area_mw2": _area(poly),
        "ntc_box_area_mw2": box * box,
        "domain_over_box_area": _area(poly) / (box * box),
        "binding_critical_branch": binding,
        "fb_flows_mw": flows,
        "ram_mw": ram,
        "prices_eur_mwh": {d: {z: float(n.buses_t.marginal_price.iloc[0][z]) for z in ZONES} for d, n in nets.items()},
        "ptdf_slack_A": {line: {z: float(H.loc[line, z]) for z in ZONES} for line in LINES},
    }


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    poly = domain_polygon()
    closed = np.vstack([poly, poly[:1]])
    box = 2 * NTC_MW
    box_pts = [(-box, -box), (box, -box), (box, box), (-box, box), (-box, -box)]
    datasets = {
        "domain": charts.dataset(["x", "y"], closed.tolist()),
        "box": charts.dataset(["x", "y"], [list(p) for p in box_pts]),
        "points": charts.dataset(["x", "y", "design"], [[net_positions(n)["A"], net_positions(n)["B"], d] for d, n in nets.items()]),
    }
    palette = charts.Palette()
    series = [
        {"type": "line", "name": "flow-based domain", "datasetId": "domain", "encode": {"x": "x", "y": "y"},
         "showSymbol": False, "areaStyle": {"opacity": 0.15}, **palette.style("flow-based domain", line=True)},
        {"type": "line", "name": "NTC box", "datasetId": "box", "encode": {"x": "x", "y": "y"}, "showSymbol": False,
         **palette.style("NTC box", line=True)},
        {"type": "scatter", "name": "cleared net positions", "datasetId": "points", "encode": {"x": "x", "y": "y", "tooltip": ["design", "x", "y"]},
         "symbolSize": 12, "label": {"show": True, "formatter": "{@design}", "position": "right", "fontSize": 11},
         **palette.style("cleared net positions", line=False)},
    ]
    option = {
        "dataset": [{"id": "domain"}, {"id": "box"}, {"id": "points"}],
        "tooltip": {"trigger": "item"},
        "grid": {**charts.GRID, "left": charts.AXIS_NAME_MARGIN, "bottom": 24},
        "xAxis": charts.x_value_axis("Net position of A (MW export)"),
        "yAxis": charts.value_axis("Net position of B (MW export)"),
        "series": series,
        "legend": {**charts.LEGEND, "data": [s["name"] for s in series]},
    }
    domain = bundle.Figure(option, datasets, title="Flow-based domain and the NTC box", height=420,
                           caption="Every point is a pair of zonal net positions (C balances the two). The polygon is "
                           "what the lines can carry after the reliability margin; the box is what fixed bilateral "
                           "limits allow. The flow-based clearing sits on the polygon's edge, the NTC clearing on the "
                           "box's, and the nodal one just outside the polygon because it may use the full ratings.")
    designs = list(nets)
    option, ds = charts.bars(ZONES, {d: net_positions(n).round(1).tolist() for d, n in nets.items()}, "MW export", horizontal=False, category_name="zone")
    np_fig = bundle.Figure(option, ds, title="Net positions by design",
                           caption="Cheap A exports, B and C import; the flow-based design lets A export more because "
                           "it accounts for the loop flow through C instead of capping each border.")
    option, ds = charts.bars(designs, {"cost": [round(float(nets[d].objective), 1) for d in designs]}, "EUR/h", horizontal=False, category_name="design")
    cost_fig = bundle.Figure(option, ds, title="Dispatch cost by design",
                             caption="Nodal is the physical optimum; flow-based gets close; NTC pays for the margin "
                             "its fixed limits waste.")
    return {"flow_based_domain": domain, "net_positions": np_fig, "cost_by_design": cost_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = {d: solve_design(d) for d in ("nodal", "NTC", "flow-based")}
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
