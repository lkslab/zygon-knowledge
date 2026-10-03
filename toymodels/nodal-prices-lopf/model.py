# SPDX-License-Identifier: MIT
"""nodal-prices-lopf: a three-bus meshed AC network with one congested line.

Linear optimal power flow: Kirchhoff's voltage law ties the flows on the three lines
of the triangle together, so when the cheap bus cannot export any more through the
small line, the price splits by bus. The load is scaled through six levels to show the
prices converge at low load and diverge once the line binds.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, run  # noqa: E402

SLUG = "nodal-prices-lopf"
TITLE = "Nodal prices in a congested triangle"

BUSES = ["A", "B", "C"]
# generator per bus: (carrier, capacity MW, marginal cost EUR/MWh)
GENS = {"A": ("coal", 1000, 20), "B": ("CCGT", 1000, 60), "C": ("oil", 500, 120)}
LOADS = {"A": 100, "B": 600, "C": 400}  # MW at load level 1.0
LINES = {"A-B": ("A", "B", 400), "B-C": ("B", "C", 1000), "A-C": ("A", "C", 1000)}  # s_nom MW
X_PU = 0.1  # equal reactance on every line, so flows split by KVL alone
LOAD_LEVELS = [0.5, 0.7, 0.9, 1.0, 1.1, 1.2]


def build(*, load_levels: list[float] | None = None, s_nom_ab: float = 400) -> pypsa.Network:
    levels = load_levels or LOAD_LEVELS
    n = pypsa.Network()
    # integer snapshots (PyPSA refuses string labels); the case label travels in the network's meta
    n.set_snapshots(pd.RangeIndex(len(levels), name="snapshot"))
    n.meta = {"load_labels": [f"{int(round(100 * lv))}% load" for lv in levels]}
    n.add("Carrier", ["AC", "coal", "CCGT", "oil", "load shedding"])
    n.add("Bus", BUSES, v_nom=380, carrier="AC")
    for bus, (carrier, p_nom, mc) in GENS.items():
        n.add("Generator", f"{carrier} {bus}", bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc)
        n.add("Generator", f"shed {bus}", bus=bus, carrier="load shedding", p_nom=1e4, marginal_cost=3000)
        n.add("Load", f"load {bus}", bus=bus, carrier="load", p_set=[LOADS[bus] * lv for lv in levels])
    for name, (b0, b1, s_nom) in LINES.items():
        n.add("Line", name, bus0=b0, bus1=b1, x=X_PU, r=0.01, s_nom=s_nom if name != "A-B" else s_nom_ab, carrier="AC")
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def _labels(n: pypsa.Network) -> pd.Series:
    """Display label of every snapshot: the load level it solves."""
    return pd.Series(n.meta["load_labels"], index=n.snapshots)


def _prices(n: pypsa.Network) -> pd.DataFrame:
    return n.buses_t.marginal_price[BUSES]


def _rent(n: pypsa.Network) -> pd.DataFrame:
    """Congestion rent per line and snapshot: |flow| times the price difference it bridges."""
    p0 = n.lines_t.p0
    lmp = _prices(n)
    rent = pd.DataFrame(index=n.snapshots, columns=list(LINES), dtype=float)
    for name, (b0, b1, _) in LINES.items():
        rent[name] = p0[name] * (lmp[b1] - lmp[b0])
    return rent


def numbers(n: pypsa.Network) -> dict:
    lmp = _prices(n)
    peak = n.snapshots[-1]
    rent = _rent(n)
    copper = build(s_nom_ab=1e5)
    solve(copper)
    loading = (n.lines_t.p0.abs() / n.lines.s_nom).loc[peak]
    return {
        "peak_prices_eur_mwh": {b: float(lmp.loc[peak, b]) for b in BUSES},
        "peak_price_spread_eur_mwh": float(lmp.loc[peak].max() - lmp.loc[peak].min()),
        "congestion_rent_peak_eur_h": float(rent.loc[peak].sum()),
        "congestion_rent_by_line_peak_eur_h": {k: float(v) for k, v in rent.loc[peak].items()},
        "line_loading_peak_pct": {k: float(100 * v) for k, v in loading.items()},
        "marginal_value_line_ab_peak_eur_mw_h": float(rent.loc[peak, "A-B"] / n.lines.s_nom["A-B"]),
        "cost_of_congestion_eur": float(n.objective - copper.objective),
        "first_congested_level": next((_labels(n)[s] for s in n.snapshots if n.lines_t.p0.abs().loc[s, "A-B"] >= 0.999 * n.lines.s_nom["A-B"]), None),
        "loop_flow_share_peak": float(n.lines_t.p0.abs().loc[peak, "A-C"] / (n.lines_t.p0.abs().loc[peak, ["A-B", "A-C"]].sum())),
    }


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    lmp = _prices(n).round(2)
    levels = list(_labels(n))
    lmp = lmp.set_axis(levels)
    option, ds = charts.bars(BUSES, {lv: lmp.loc[lv].tolist() for lv in levels}, "EUR/MWh", category_name="bus")
    prices = bundle.Figure(option, ds, title="Nodal prices by load level",
                           caption="One price while the network is unconstrained; once line A-B hits its limit the cheap "
                           "bus A decouples and B and C pay their own marginal units.")
    peak = n.snapshots[-1]
    flows = n.lines_t.p0.loc[peak].abs().round(1)
    option, ds = charts.bars(list(LINES), {"flow": flows.tolist(), "capacity": n.lines.s_nom.tolist()}, "MW",
                             horizontal=True, category_name="line")
    flow_fig = bundle.Figure(option, ds, title="Line flows at peak load", caption="Absolute flow against thermal limit; A-B is at its limit, the loop path A-C carries the rest.")
    rent = _rent(n).round(1).set_axis(levels)
    option, ds = charts.bars(list(LINES), {lv: rent.loc[lv].tolist() for lv in levels}, "EUR/h", category_name="line")
    rent_fig = bundle.Figure(option, ds, title="Congestion rent by line",
                             caption="Flow times the price difference across the line, the merchandising surplus a "
                             "transmission owner collects; zero until a constraint binds. B-C goes negative: "
                             "Kirchhoff's voltage law forces flow against the price gradient on the loop path.")
    return {"nodal_prices": prices, "line_flows": flow_fig, "congestion_rent_by_line": rent_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
