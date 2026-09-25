# SPDX-License-Identifier: MIT
"""redispatch: a zonal market that ignores an internal bottleneck, then the grid
operator's redispatch to make the schedule feasible, compared with nodal pricing.

Four buses: a windy, cheap north and a load-heavy south joined by two small lines.
Three solves: (1) the nodal reference, (2) a copper-plate zonal market that clears
as if the lines were infinite, (3) redispatch: the market dispatch is frozen and
every unit gets an up-twin and a down-twin the operator can call at a cost, so the
flows fit the real grid. The gap between (2)+(3) and (1) is the price of pretending.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "redispatch"
TITLE = "Zonal market, redispatch and nodal pricing"

BUSES = ["N1", "N2", "S1", "S2"]
GENS = {  # name: (bus, carrier, p_nom MW, marginal cost)
    "onwind N1": ("N1", "onwind", 3000, 0),
    "coal N2": ("N2", "coal", 1000, 30),
    "CCGT S1": ("S1", "CCGT", 2000, 60),
    "OCGT S2": ("S2", "OCGT", 1500, 120),
}
LOADS = {"N1": 300, "N2": 300, "S1": 1500, "S2": 1500}  # MW, scaled by a daily shape
LINES = {"N1-N2": ("N1", "N2", 2000), "S1-S2": ("S1", "S2", 2000), "N1-S1": ("N1", "S1", 400), "N2-S2": ("N2", "S2", 400)}
X_PU = 0.1
REDISPATCH_PREMIUM = 10  # EUR/MWh paid on top of cost for ramping a unit up; down-ramps refund cost minus this
VOLL = 3000


def build(*, copper_plate: bool = False) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(1))
    n.add("Carrier", ["AC", "onwind", "coal", "CCGT", "OCGT", "load shedding"])
    n.add("Bus", BUSES, v_nom=380, carrier="AC")
    shape = profiles.daily_load(n.snapshots, 0.7, 1.0, noise=0.0)
    for name, (bus, carrier, p_nom, mc) in GENS.items():
        kw = {"p_max_pu": profiles.wind(n.snapshots, mean_cf=0.5)} if carrier == "onwind" else {}
        n.add("Generator", name, bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc, **kw)
    for bus, mw in LOADS.items():
        n.add("Load", f"load {bus}", bus=bus, carrier="load", p_set=shape * mw)
        n.add("Generator", f"shed {bus}", bus=bus, carrier="load shedding", p_nom=1e4, marginal_cost=VOLL)
    for name, (b0, b1, s_nom) in LINES.items():
        n.add("Line", name, bus0=b0, bus1=b1, x=X_PU, r=0.01, carrier="AC", s_nom=s_nom * (100 if copper_plate else 1))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def build_redispatch(market: pypsa.Network) -> pypsa.Network:
    """Freeze the market dispatch on the real grid and add ramp-up / ramp-down twins."""
    n = build()
    p_market = market.generators_t.p
    for name, (bus, carrier, p_nom, mc) in GENS.items():
        share = (p_market[name] / p_nom).clip(0, 1)
        n.generators_t.p_min_pu[name] = share
        n.generators_t.p_max_pu[name] = share
        # ramp up: remaining headroom at cost plus premium; wind headroom follows its availability
        avail = market.generators_t.p_max_pu[name] if name in market.generators_t.p_max_pu else pd.Series(1.0, index=n.snapshots)
        n.add("Generator", f"{name} up", bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=mc + REDISPATCH_PREMIUM,
              p_max_pu=(avail - share).clip(lower=0))
        # ramp down: negative generation up to the scheduled amount, refunding the avoided cost minus the premium
        n.add("Generator", f"{name} down", bus=bus, carrier=carrier, p_nom=p_nom, marginal_cost=-(mc - REDISPATCH_PREMIUM),
              p_min_pu=-share, p_max_pu=0)
    return n


def stages() -> dict[str, pypsa.Network]:
    nodal = solve(build())
    market = solve(build(copper_plate=True))
    redispatch = solve(build_redispatch(market))
    return {"nodal": nodal, "zonal market": market, "redispatch": redispatch}


def _cost(n: pypsa.Network) -> float:
    return float(n.objective)


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    nodal, market, rd = nets["nodal"], nets["zonal market"], nets["redispatch"]
    up = rd.generators_t.p[[c for c in rd.generators.index if c.endswith(" up")]]
    down = rd.generators_t.p[[c for c in rd.generators.index if c.endswith(" down")]]
    rd_cost = _cost(rd) - _cost(market)
    wind_avail = (market.generators_t.p_max_pu["onwind N1"] * GENS["onwind N1"][2]).sum()
    return {
        "cost_nodal_eur": _cost(nodal),
        "cost_zonal_market_eur": _cost(market),
        "cost_redispatch_eur": rd_cost,
        "cost_zonal_plus_redispatch_eur": _cost(rd),
        "efficiency_loss_pct": float(100 * (_cost(rd) - _cost(nodal)) / _cost(nodal)),
        "redispatch_up_mwh": float(up.sum().sum()),
        "redispatch_down_mwh": float(-down.sum().sum()),
        "redispatch_by_unit_mwh": {g: {"up": float(up[f"{g} up"].sum()), "down": float(-down[f"{g} down"].sum())} for g in GENS},
        "wind_curtailed_mwh": {"nodal": float(wind_avail - nodal.generators_t.p["onwind N1"].sum()),
                               "zonal market": float(wind_avail - market.generators_t.p["onwind N1"].sum()),
                               "after redispatch": float(wind_avail - (market.generators_t.p["onwind N1"] + rd.generators_t.p["onwind N1 down"]).sum())},
        "avg_price_eur_mwh": {"nodal": {b: float(nodal.buses_t.marginal_price[b].mean()) for b in BUSES},
                              "zonal market": float(market.buses_t.marginal_price[BUSES].mean().mean())},
        "max_line_loading_market_pct": float(100 * (market.lines_t.p0.abs() / (market.lines.s_nom / 100)).max().max()),
    }


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    nodal, market, rd = nets["nodal"], nets["zonal market"], nets["redispatch"]
    stages_ = ["nodal", "zonal market", "zonal + redispatch"]
    option, ds = charts.bars(stages_, {"cost": [round(_cost(nodal) / 1e3, 1), round(_cost(market) / 1e3, 1), round(_cost(rd) / 1e3, 1)]}, "kEUR/day", category_name="stage")
    cc = bundle.Figure(option, ds, title="Daily system cost by market design",
                       caption="The zonal market looks cheapest because it ignores the bottleneck; once the operator "
                       "pays for redispatch the day costs more than nodal pricing would have.")
    up = {name: float(rd.generators_t.p[f"{name} up"].sum()) for name in GENS}
    down = {name: float(-rd.generators_t.p[f"{name} down"].sum()) for name in GENS}
    option, ds = charts.bars(list(GENS), {"ramp up": [round(up[g], 1) for g in GENS], "ramp down": [round(-down[g], 1) for g in GENS]}, "MWh", category_name="unit")
    vol = bundle.Figure(option, ds, title="Redispatch volumes by unit",
                        caption="Northern wind is turned down and southern gas turned up so the north-south lines "
                        "hold. Volumes are what the market schedule got wrong about the grid.")
    loading = pd.DataFrame({ln: (market.lines_t.p0[ln].abs() / (market.lines.s_nom[ln] / 100) * 100).round(1) for ln in LINES})
    option, ds = charts.time_series(loading, "% of limit")
    option["series"][0]["markLine"] = {**charts.mark_lines([{"value": 100, "label": "limit"}], axis="yAxis")}
    ll = bundle.Figure(option, ds, title="Line loading implied by the zonal schedule",
                       caption="Flows the market schedule would push through the real grid: the two north-south "
                       "lines run far above their limit, which is the redispatch need.")
    return {"cost_comparison": cc, "redispatch_volume": vol, "line_loading": ll}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = stages()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
