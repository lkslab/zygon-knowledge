# SPDX-License-Identifier: MIT
"""chp-heat-power: two kinds of combined heat and power plant serving an electricity
and a heat load over a winter fortnight, beside a gas boiler and a heat pump.

A backpressure unit has a fixed heat-to-power ratio: one Link with two outputs. An
extraction-condensing unit can trade power for heat inside a feasible region bounded by
the iso-fuel line (every unit of heat costs c_v units of power) and the backpressure
line (power at least c_m times heat); that region is two custom linopy constraints on
two Links sharing one fuel budget.
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

SLUG = "chp-heat-power"
TITLE = "Backpressure and extraction CHP against a boiler and a heat pump"

GAS_COST = 30.0  # EUR/MWh thermal
ETA_EL, C_V, C_M = 0.45, 0.15, 0.75  # extraction CHP: electric efficiency, iso-fuel slope, backpressure ratio
FUEL_MAX_EXTRACTION = 200.0  # MW fuel
BACKPRESSURE = dict(fuel_mw=100.0, eta_el=0.40, eta_th=0.45)
BOILER_MW_TH, BOILER_ETA = 120.0, 0.9
HEAT_PUMP_MW_EL, COP = 25.0, 2.8
WIND_MW, OCGT_MW = 150.0, 200.0
EL_BASE, EL_PEAK = 70.0, 130.0
HEAT_MEAN_MW = 110.0
DAYS = 14
P_MAX = ETA_EL * FUEL_MAX_EXTRACTION  # 90 MW electric at full condensing


def build() -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(DAYS, start="2025-01-08"))
    n.add("Carrier", ["AC", "gas", "heat", "onwind", "OCGT", "CHP", "CHP extraction", "gas boiler", "heat pump", "load shedding"])
    n.add("Bus", ["electricity", "heat", "gas"], carrier=["AC", "heat", "gas"])
    n.add("Generator", "gas", bus="gas", carrier="gas", p_nom=1e4, marginal_cost=GAS_COST)
    n.add("Generator", "onwind", bus="electricity", carrier="onwind", p_nom=WIND_MW, p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", "OCGT", bus="electricity", carrier="OCGT", p_nom=OCGT_MW, marginal_cost=120.0)
    n.add("Generator", "load shedding", bus="electricity", carrier="load shedding", p_nom=1e4, marginal_cost=3000)
    n.add("Generator", "heat shedding", bus="heat", carrier="load shedding", p_nom=1e4, marginal_cost=3000)
    n.add("Load", "electricity demand", bus="electricity", carrier="load", p_set=profiles.daily_load(n.snapshots, EL_BASE, EL_PEAK))
    year = profiles.year_index(1)
    heat = profiles.heat(year, HEAT_MEAN_MW * 0.55).loc[n.snapshots]  # the January slice of a year-shaped demand
    n.add("Load", "heat demand", bus="heat", carrier="heat", p_set=heat)
    # backpressure CHP: one link, two outputs, fixed ratio
    bp = BACKPRESSURE
    n.add("Link", "CHP", bus0="gas", bus1="electricity", bus2="heat", carrier="CHP", p_nom=bp["fuel_mw"],
          efficiency=bp["eta_el"], efficiency2=bp["eta_th"])
    # extraction CHP: two links drawing on the same fuel; the heat link's "efficiency" is
    # eta_el / c_v so that its fuel draw equals the power given up per unit of heat
    n.add("Link", "CHP extraction power", bus0="gas", bus1="electricity", carrier="CHP extraction", p_nom=FUEL_MAX_EXTRACTION, efficiency=ETA_EL)
    n.add("Link", "CHP extraction heat", bus0="gas", bus1="heat", carrier="CHP extraction", p_nom=FUEL_MAX_EXTRACTION, efficiency=ETA_EL / C_V)
    n.add("Link", "gas boiler", bus0="gas", bus1="heat", carrier="gas boiler", p_nom=BOILER_MW_TH / BOILER_ETA, efficiency=BOILER_ETA)
    n.add("Link", "heat pump", bus0="electricity", bus1="heat", carrier="heat pump", p_nom=HEAT_PUMP_MW_EL, efficiency=COP)
    return n


def chp_region(n: pypsa.Network, snapshots) -> None:
    """The extraction plant's feasible region as two linopy constraints on its links.

    Fuel draws p_power and p_heat (MW fuel): iso-fuel top line p_power + p_heat <= F_max;
    backpressure line P >= c_m Q, i.e. eta_el p_power >= c_m (eta_el / c_v) p_heat.
    """
    p = n.model["Link-p"]
    power = p.sel(name="CHP extraction power")
    heat = p.sel(name="CHP extraction heat")
    n.model.add_constraints(power + heat <= FUEL_MAX_EXTRACTION, name="chp-iso-fuel")
    n.model.add_constraints(power - (C_M / C_V) * heat >= 0, name="chp-backpressure")


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n, extra_functionality=chp_region)


def outputs(n: pypsa.Network) -> pd.DataFrame:
    """Power and heat outputs (MW) and fuel (MW) of both CHPs, boiler and heat pump."""
    L = n.links_t
    return pd.DataFrame({
        "extraction P": -L.p1["CHP extraction power"],
        "extraction Q": -L.p1["CHP extraction heat"],
        "extraction fuel": L.p0["CHP extraction power"] + L.p0["CHP extraction heat"],
        "backpressure P": -L.p1["CHP"],
        "backpressure Q": -L.p2["CHP"],
        "backpressure fuel": L.p0["CHP"],
        "boiler Q": -L.p1["gas boiler"],
        "heat pump Q": -L.p1["heat pump"],
    })


def numbers(n: pypsa.Network) -> dict:
    o = outputs(n)
    heat_total = n.loads_t.p_set["heat demand"].sum()
    q_ext, p_ext, f_ext = o["extraction Q"].sum(), o["extraction P"].sum(), o["extraction fuel"].sum()
    q_bp, p_bp, f_bp = o["backpressure Q"].sum(), o["backpressure P"].sum(), o["backpressure fuel"].sum()
    price = n.buses_t.marginal_price
    return {
        "heat_share_pct": {"CHP extraction": float(100 * q_ext / heat_total), "CHP": float(100 * q_bp / heat_total),
                           "gas boiler": float(100 * o["boiler Q"].sum() / heat_total), "heat pump": float(100 * o["heat pump Q"].sum() / heat_total)},
        "extraction_heat_to_power_ratio": float(q_ext / p_ext) if p_ext > 0 else None,
        "extraction_fuel_utilisation_pct": float(100 * (p_ext + q_ext) / f_ext) if f_ext > 0 else None,
        "backpressure_fuel_utilisation_pct": float(100 * (p_bp + q_bp) / f_bp) if f_bp > 0 else None,
        "hours_extraction_on_backpressure_line_pct": float(100 * ((o["extraction P"] - C_M * o["extraction Q"]).abs() < 1e-3).mean()),
        "hours_extraction_full_condensing_pct": float(100 * ((o["extraction Q"] < 1e-3) & (o["extraction P"] > 1e-3)).mean()),
        "mean_price_eur_mwh": {"electricity": float(price["electricity"].mean()), "heat": float(price["heat"].mean())},
        "heat_price_range_eur_mwh": [float(price["heat"].min()), float(price["heat"].max())],
        "gas_burned_gwh": float((n.generators_t.p["gas"]).sum() / 1e3),
        "total_cost_meur": float(n.objective / 1e6),
        "electricity_from_chp_pct": float(100 * (p_ext + p_bp) / n.loads_t.p_set["electricity demand"].sum()),
    }


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    o = outputs(n)
    q_star = P_MAX / (C_M + C_V)
    grid = np.linspace(0, q_star * 1.1, 40)
    region = pd.DataFrame({"iso-fuel line": np.clip(P_MAX - C_V * grid, 0, None), "backpressure line": C_M * grid},
                          index=pd.Index(grid.round(2), name="heat"))
    region.loc[region.index > q_star, "backpressure line"] = np.nan
    region.loc[region.index > q_star, "iso-fuel line"] = np.nan
    option, ds = charts.xy_lines(region.round(2), "Heat output (MW thermal)", "MW electric", x_extra={"min": 0})
    pts = o[["extraction Q", "extraction P"]].round(2).drop_duplicates()
    ds["points"] = charts.dataset(["heat", "power"], pts.to_numpy().tolist())
    option["dataset"].append({"id": "points"})
    option["series"].append({"type": "scatter", "name": "operating points", "datasetId": "points", "encode": {"x": "heat", "y": "power"},
                             "symbolSize": 6, "itemStyle": {"color": "#6b7280", "opacity": 0.6}})
    option["legend"]["data"].append("operating points")
    # the region itself, filled between the two lines with the stack trick (a transparent lower edge, the depth on top)
    qs = np.linspace(0, q_star, 20)
    lower, upper = C_M * qs, P_MAX - C_V * qs
    ds["region"] = charts.dataset(["heat", "lower", "depth"], [[q, lo, hi - lo] for q, lo, hi in zip(qs, lower, upper)])
    option["dataset"].append({"id": "region"})
    edge = {"type": "line", "name": "what the unit can do", "datasetId": "region", "showSymbol": False, "silent": True,
            "stack": "region", "stackStrategy": "all", "lineStyle": {"width": 0, "opacity": 0},
            "itemStyle": {"color": charts.BAND_BELOW}}
    option["series"][:0] = [{**edge, "encode": {"x": "heat", "y": "lower"}},
                            {**edge, "encode": {"x": "heat", "y": "depth"}, "areaStyle": {"color": charts.BAND_BELOW, "opacity": 0.18}}]
    option["legend"]["data"].insert(0, "what the unit can do")
    option["tooltip"] = {"trigger": "item"}
    reg = bundle.Figure(option, ds, title="Feasible region of the extraction CHP",
                        caption="Power against heat: the iso-fuel line is full fuel, giving up c_v MW of power per MW of "
                        "heat; the backpressure line is the most heat the turbine can extract for the power it makes. "
                        "The unit can run anywhere in the green region. Most hours it sits on the backpressure line, "
                        "making the most heat; when power is dear it moves up into the region, condensing more power.")
    heat_stack = pd.DataFrame({"CHP extraction": o["extraction Q"], "CHP": o["backpressure Q"], "gas boiler": o["boiler Q"], "heat pump": o["heat pump Q"]}).round(1)
    option, ds = charts.time_series(heat_stack, "MW thermal", stack=True, area=True, slider=False)
    hs = bundle.Figure(option, ds, title="Heat supply over the fortnight",
                       caption="The backpressure unit runs flat, the extraction unit follows the heat load, the boiler "
                       "and the heat pump take the peaks; which one depends on the electricity price of the hour.")
    pq = pd.DataFrame({"extraction P": o["extraction P"], "extraction Q": o["extraction Q"], "price": n.buses_t.marginal_price["electricity"]}).round(2)
    option, ds = charts.dual_axis(pq, ["extraction P", "extraction Q"], ["price"], "MW", "EUR/MWh")
    pqf = bundle.Figure(option, ds, title="Extraction CHP: power and heat against the electricity price",
                        caption="When the price rises the unit condenses more (power up, heat down) and the boiler "
                        "covers the heat; when wind pushes the price down it extracts more heat.")
    return {"chp_feasible_region": reg, "heat_supply": hs, "power_vs_heat": pqf}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
