# SPDX-License-Identifier: MIT
"""sector-coupling-single-node: electricity, heat and hydrogen on one node.

The single-node capacity expansion gains a heat bus (heat pump with a seasonal COP, gas
boiler, hot-water tank, winter-peaked heat demand) and a hydrogen bus (electrolyser,
store, fuel cell, a flat industrial hydrogen demand) under a tight CO2 cap. Coupling
adds flexible electric load: the heat pump and electrolyser run when wind and solar
are surplus, and the tank and hydrogen store carry that energy across hours and weeks.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, profiles, run  # noqa: E402

SLUG = "sector-coupling-single-node"
TITLE = "Sector coupling: electricity, heat and hydrogen"

BASE = run.load_model("capacity-expansion-single-node")
MEAN_HEAT_MW = 60  # thermal
H2_DEMAND_MW = 20  # MW of hydrogen, flat
CAP_FRACTION = 0.2  # of the electricity-only unconstrained emissions
HEAT_TECH = {
    "heat pump": dict(overnight=600, life=20, fom=1.5),  # per kW electric
    "gas boiler": dict(overnight=100, life=20, fom=1.0, eta=0.9, marginal_cost=60 / 0.9),
    "water tanks": dict(overnight=3, life=25, fom=1.0, loss=0.005),  # EUR/kWh, standing loss per hour
}
CO2_GAS_BOILER = BASE.CO2_CCGT / 0.9  # t per MWh_th from a 90 % boiler
EL_CARRIERS = ["onwind", "solar", "CCGT", "battery", "H2 Fuel Cell"]
EL_WITHDRAW = ["load", "heat pump", "H2 Electrolysis", "battery"]
HEAT_CARRIERS = ["heat pump", "gas boiler", "water tanks"]


def _capex(spec: dict) -> float:
    return finance.capital_cost(spec["overnight"], spec["life"], fom_pct=spec["fom"])


def build(*, cap_fraction: float = CAP_FRACTION) -> pypsa.Network:
    n = BASE.build(co2_cap_t=cap_fraction * BASE.reference_emissions())
    n.add("Carrier", "gas boiler", co2_emissions=CO2_GAS_BOILER)
    n.add("Carrier", ["heat", "heat pump", "water tanks"])
    n.add("Bus", "heat", carrier="heat")
    n.add("Load", "heat demand", bus="heat", carrier="heat", p_set=profiles.heat(n.snapshots, MEAN_HEAT_MW))
    n.add("Link", "heat pump", bus0="electricity", bus1="heat", carrier="heat pump", p_nom_extendable=True,
          capital_cost=_capex(HEAT_TECH["heat pump"]), efficiency=profiles.cop(n.snapshots))
    gb = HEAT_TECH["gas boiler"]
    n.add("Generator", "gas boiler", bus="heat", carrier="gas boiler", p_nom_extendable=True,
          capital_cost=_capex(gb), marginal_cost=gb["marginal_cost"], efficiency=1.0)
    wt = HEAT_TECH["water tanks"]
    n.add("Store", "water tanks", bus="heat", carrier="water tanks", e_nom_extendable=True, e_cyclic=True,
          capital_cost=_capex(wt), standing_loss=wt["loss"])
    n.add("Load", "H2 demand", bus="hydrogen", carrier="H2", p_set=H2_DEMAND_MW)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def balance(n: pypsa.Network, bus: str) -> pd.DataFrame:
    """Signed power per carrier at one bus: supply positive, withdrawal negative (MW)."""
    cols: dict[str, pd.Series] = {}
    for g in n.generators[n.generators.bus == bus].index:
        cols[n.generators.carrier[g]] = cols.get(n.generators.carrier[g], 0) + n.generators_t.p[g]
    for s in n.storage_units[n.storage_units.bus == bus].index:
        cols[n.storage_units.carrier[s]] = n.storage_units_t.p[s]
    for st in n.stores[n.stores.bus == bus].index:
        cols[n.stores.carrier[st]] = n.stores_t.p[st]
    for lk in n.links.index:
        if n.links.bus0[lk] == bus:
            cols[n.links.carrier[lk]] = -n.links_t.p0[lk]
        elif n.links.bus1[lk] == bus:
            cols[n.links.carrier[lk]] = -n.links_t.p1[lk]  # p1 is negative when delivering
    for ld in n.loads[n.loads.bus == bus].index:
        cols["load"] = -n.loads_t.p_set[ld] if "load" not in cols else cols["load"] - n.loads_t.p_set[ld]
    return pd.DataFrame(cols)


def numbers(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    heat = balance(n, "heat")
    elec = balance(n, "electricity")
    heat_demand = float((n.loads_t.p_set["heat demand"] * w).sum())
    hp_heat = float((heat["heat pump"].clip(lower=0) * w).sum())
    boiler_heat = float((heat["gas boiler"].clip(lower=0) * w).sum())
    hp_el = float((n.links_t.p0["heat pump"] * w).sum())
    ely_el = float((n.links_t.p0["H2 Electrolysis"] * w).sum())
    el_demand = float((n.loads_t.p_set["demand"] * w).sum())
    cr = finance.cost_recovery(n)
    h2_out = float((n.links_t.p0["H2 Electrolysis"] * n.links.efficiency["H2 Electrolysis"] * w).sum())
    h2_cost = float(cr.loc[["H2 Electrolysis", "H2 Store"], "cost"].sum()) + float((n.buses_t.marginal_price["electricity"] * n.links_t.p0["H2 Electrolysis"] * w).sum())
    price = n.buses_t.marginal_price
    return {
        "total_cost_meur_a": float(n.objective / 1e6),
        "heat_pump_share_of_heat_pct": float(100 * hp_heat / (hp_heat + boiler_heat)),
        "heat_supplied_over_demand_pct": float(100 * (hp_heat + boiler_heat) / heat_demand),
        "seasonal_cop_mean": float(hp_heat / hp_el) if hp_el > 0 else None,
        "capacity_mw": {**{c: float(v) for c, v in BASE.capacities_mw(n).items()},
                        "heat pump (el)": float(n.links.p_nom_opt["heat pump"]), "gas boiler (th)": float(n.generators.p_nom_opt["gas boiler"])},
        "storage_mwh": {"water tanks": float(n.stores.e_nom_opt["water tanks"]), "H2 Store": float(n.stores.e_nom_opt["H2 Store"])},
        "electricity_demand_uplift_pct": float(100 * (hp_el + ely_el) / el_demand),
        "electrolyser_capacity_factor_pct": float(100 * ely_el / (n.links.p_nom_opt["H2 Electrolysis"] * 8760)) if n.links.p_nom_opt["H2 Electrolysis"] > 1e-3 else None,
        "lcoh_eur_mwh": float(h2_cost / h2_out) if h2_out > 0 else None,
        "mean_price_eur_mwh": {"electricity": float((price["electricity"] * w).sum() / w.sum()), "heat": float((price["heat"] * w).sum() / w.sum()), "hydrogen": float((price["hydrogen"] * w).sum() / w.sum())},
        "co2_price_eur_t": float(-n.global_constraints.mu["co2_limit"]),
        "emissions_kt": float(BASE.emissions_t(n) / 1e3 + (heat["gas boiler"] * w).sum() * CO2_GAS_BOILER / 1e3),
        "load_shed_mwh": float((n.generators_t.p["load shedding"] * w).sum()),
    }


def _weekly(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("1W").mean()


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    elec = balance(n, "electricity")
    cols = list(dict.fromkeys(c for c in EL_CARRIERS + EL_WITHDRAW if c in elec.columns))
    weekly = _weekly(elec[cols]).round(1)
    supply = weekly.clip(lower=0)
    withdraw = weekly.clip(upper=0)
    df = pd.concat([supply[[c for c in cols if (supply[c] > 0).any()]], withdraw[[c for c in cols if (withdraw[c] < 0).any()]].add_suffix(" (withdrawal)")], axis=1)
    option, ds = charts.time_series(df, "MW (weekly mean)", stack=True, area=True, negative_stack=[c for c in df.columns if c.endswith("(withdrawal)")], slider=False)
    for s in option["series"]:  # withdrawal series carry the carrier's colour in the client via the base name
        s["name"] = s["name"]
    eb_el = bundle.Figure(option, ds, title="Electricity balance, weekly means",
                          caption="Supply above zero, withdrawals below. The heat pump's draw peaks in winter, the "
                          "electrolyser soaks up summer solar; the fuel cell returns a little of it in the dark weeks.")
    heat = balance(n, "heat")
    hcols = [c for c in HEAT_CARRIERS + ["load"] if c in heat.columns]
    wh = _weekly(heat[hcols]).round(1)
    dfh = pd.concat([wh.clip(lower=0)[[c for c in hcols if (wh[c] > 0).any()]], wh.clip(upper=0)[[c for c in hcols if (wh[c] < 0).any()]].add_suffix(" (withdrawal)")], axis=1)
    option, ds = charts.time_series(dfh, "MW thermal (weekly mean)", stack=True, area=True, negative_stack=[c for c in dfh.columns if c.endswith("(withdrawal)")], slider=False)
    eb_heat = bundle.Figure(option, ds, title="Heat balance, weekly means",
                            caption="At this cap the CO2 shadow price prices the gas boiler out entirely, so the heat pump "
                            "carries all heat and the cheap tank absorbs surplus electricity as heat (its standing "
                            "losses are why heat supplied exceeds heat demand). Loosen the cap knob to see the boiler return.")
    week = n.snapshots[(n.snapshots >= "2025-01-15") & (n.snapshots < "2025-01-22")]
    flex = pd.DataFrame({"heat pump": n.links_t.p0.loc[week, "heat pump"], "H2 Electrolysis": n.links_t.p0.loc[week, "H2 Electrolysis"],
                         "price": n.buses_t.marginal_price.loc[week, "electricity"]}).round(2)
    option, ds = charts.dual_axis(flex, ["heat pump", "H2 Electrolysis"], ["price"], "MW electric", "EUR/MWh", step="middle")
    fl = bundle.Figure(option, ds, title="Flexible load in a winter week",
                       caption="Electric draw of the heat pump and the electrolyser against the electricity price: the "
                       "electrolyser stops when the price rises, the heat pump keeps going because the tank is small.")
    return {"energy_balance_electricity": eb_el, "energy_balance_heat": eb_heat, "flexible_load_week": fl}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
