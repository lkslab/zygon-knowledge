# SPDX-License-Identifier: MIT
"""capacity-expansion-single-node: greenfield investment in wind, solar, gas, a battery
and a hydrogen chain against a stylised year of load, under a sweep of CO2 caps.

The optimiser co-decides capacities and hourly dispatch to minimise annualised capital
plus operating cost. Tightening the CO2 cap moves the mix from gas to wind and solar,
then to storage and hydrogen for the last few percent, and raises the CO2 shadow price.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, profiles, run  # noqa: E402

SLUG = "capacity-expansion-single-node"
TITLE = "Single-node capacity expansion under a CO2 cap"

EVERY_H = 4  # snapshot resolution of the stylised year (2190 snapshots)
MEAN_LOAD_MW = 100
VOLL = 3000  # EUR/MWh
CO2_CCGT = 0.37  # t/MWh_el

# overnight EUR/kW, lifetime a, FOM % of overnight per a, marginal cost EUR/MWh, misc
TECH = {
    "onwind": dict(overnight=1000, life=25, fom=2.5, marginal_cost=0.0),
    "solar": dict(overnight=600, life=25, fom=1.5, marginal_cost=0.0),
    "CCGT": dict(overnight=900, life=30, fom=2.0, marginal_cost=60.0),
    "battery": dict(overnight=1200, life=15, fom=1.0, marginal_cost=0.0, max_hours=4, eta=0.95),
    "H2 Electrolysis": dict(overnight=700, life=25, fom=2.0, marginal_cost=0.0, eta=0.70),
    "H2 Fuel Cell": dict(overnight=1000, life=15, fom=2.0, marginal_cost=0.0, eta=0.50),
    "H2 Store": dict(overnight=10, life=30, fom=1.0),  # EUR/kWh
}
CAP_FRACTIONS: dict[str, float | None] = {"no cap": None, "50%": 0.5, "20%": 0.2, "5%": 0.05, "0%": 0.0}
CARRIERS_MW = ["onwind", "solar", "CCGT", "battery", "H2 Electrolysis", "H2 Fuel Cell"]


def _capex(tech: str) -> float:
    t = TECH[tech]
    return finance.capital_cost(t["overnight"], t["life"], fom_pct=t["fom"])


def build(*, co2_cap_t: float | None = None, mean_load_mw: float = MEAN_LOAD_MW, with_h2: bool = True) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.year_index(EVERY_H))
    n.snapshot_weightings.loc[:, :] = EVERY_H
    n.add("Carrier", ["AC", "H2", "load shedding", "onwind", "solar", "battery", "H2 Electrolysis", "H2 Fuel Cell", "H2 Store"])
    n.add("Carrier", "CCGT", co2_emissions=CO2_CCGT)
    n.add("Bus", "electricity", carrier="AC")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(n.snapshots, mean_load_mw))
    n.add("Generator", "onwind", bus="electricity", carrier="onwind", p_nom_extendable=True,
          capital_cost=_capex("onwind"), marginal_cost=TECH["onwind"]["marginal_cost"], p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", "solar", bus="electricity", carrier="solar", p_nom_extendable=True,
          capital_cost=_capex("solar"), marginal_cost=TECH["solar"]["marginal_cost"], p_max_pu=profiles.solar(n.snapshots))
    n.add("Generator", "CCGT", bus="electricity", carrier="CCGT", p_nom_extendable=True,
          capital_cost=_capex("CCGT"), marginal_cost=TECH["CCGT"]["marginal_cost"], efficiency=1.0)
    n.add("Generator", "load shedding", bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=VOLL)
    b = TECH["battery"]
    n.add("StorageUnit", "battery", bus="electricity", carrier="battery", p_nom_extendable=True,
          capital_cost=_capex("battery"), max_hours=b["max_hours"], efficiency_store=b["eta"],
          efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
    if with_h2:
        n.add("Bus", "hydrogen", carrier="H2")
        n.add("Link", "H2 Electrolysis", bus0="electricity", bus1="hydrogen", carrier="H2 Electrolysis",
              p_nom_extendable=True, capital_cost=_capex("H2 Electrolysis"), efficiency=TECH["H2 Electrolysis"]["eta"])
        n.add("Link", "H2 Fuel Cell", bus0="hydrogen", bus1="electricity", carrier="H2 Fuel Cell",
              p_nom_extendable=True, capital_cost=_capex("H2 Fuel Cell"), efficiency=TECH["H2 Fuel Cell"]["eta"])
        n.add("Store", "H2 Store", bus="hydrogen", carrier="H2 Store", e_nom_extendable=True, e_cyclic=True,
              capital_cost=_capex("H2 Store"))
    if co2_cap_t is not None:
        n.add("GlobalConstraint", "co2_limit", type="primary_energy", carrier_attribute="co2_emissions",
              sense="<=", constant=co2_cap_t)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def emissions_t(n: pypsa.Network) -> float:
    w = n.snapshot_weightings.generators
    return float((n.generators_t.p["CCGT"] * w).sum() * CO2_CCGT)


def capacities_mw(n: pypsa.Network) -> pd.Series:
    cap = n.statistics.optimal_capacity(comps=["Generator", "StorageUnit", "Link"]).groupby(level="carrier").sum()
    return cap.reindex(CARRIERS_MW).fillna(0.0)


def costs_by_carrier(n: pypsa.Network) -> pd.DataFrame:
    capex = finance.by_carrier(n.statistics.capex())
    opex = finance.by_carrier(n.statistics.opex())
    df = pd.DataFrame({"capex": capex, "opex": opex}).fillna(0.0)
    return df.reindex(CARRIERS_MW + ["H2 Store", "load shedding"]).fillna(0.0)


def reference_emissions() -> float:
    """Unconstrained annual emissions in t, the base every cap is a fraction of.

    Dependant models read it from this model's committed results.yaml (`no cap`) instead
    of re-solving; if the file is missing, solve the unconstrained case.
    """
    results = Path(__file__).resolve().parent / "results.yaml"
    if results.exists():
        import yaml

        doc = yaml.safe_load(results.read_text())
        kt = doc.get("numbers", {}).get("no cap", {}).get("emissions_kt")
        if kt is not None:
            return float(kt) * 1e3
    return emissions_t(solve(build()))


def sweep(fractions: dict[str, float | None] | None = None) -> dict[str, pypsa.Network]:
    """Solve the unconstrained case, then every cap as a fraction of its emissions."""
    fractions = fractions or CAP_FRACTIONS
    base = solve(build())
    e0 = emissions_t(base)
    out: dict[str, pypsa.Network] = {}
    for label, frac in fractions.items():
        out[label] = base if frac is None else solve(build(co2_cap_t=frac * e0))
    return out


def summary(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    load = n.loads_t.p_set["demand"]
    price = n.buses_t.marginal_price["electricity"]
    demand_mwh = float((load * w).sum())
    cap = capacities_mw(n)
    supply = n.generators_t.p.mul(w, axis=0).sum()
    avail = {c: float((n.generators_t.p_max_pu[c] * cap[c] * w).sum()) for c in ("onwind", "solar")}
    vre = supply["onwind"] + supply["solar"]
    mu = float(n.global_constraints.mu.get("co2_limit", 0.0)) if len(n.global_constraints) else 0.0
    return {
        "total_cost_meur_a": float(n.objective / 1e6),
        "avg_cost_eur_mwh": float(n.objective / demand_mwh),
        "load_weighted_price_eur_mwh": float((price * load * w).sum() / demand_mwh),
        "co2_price_eur_t": float(-mu),
        "emissions_kt": float(emissions_t(n) / 1e3),
        "capacity_mw": {c: float(cap[c]) for c in CARRIERS_MW},
        "h2_store_mwh": float(n.stores.e_nom_opt.get("H2 Store", 0.0)) if len(n.stores) else 0.0,
        "capacity_factor_pct": {c: float(100 * supply[c] / (cap[c] * 8760)) if cap[c] > 1e-3 else None for c in ("onwind", "solar", "CCGT")},
        "curtailment_pct": float(100 * (1 - vre / (avail["onwind"] + avail["solar"]))) if (avail["onwind"] + avail["solar"]) > 0 else 0.0,
        "vre_share_pct": float(100 * vre / demand_mwh),
        "load_shed_mwh": float(supply["load shedding"]),
        "hours_price_above_ccgt_pct": float(100 * (price > TECH["CCGT"]["marginal_cost"] + 1).mean()),
    }


def numbers(networks: dict[str, pypsa.Network]) -> dict:
    return {label: summary(n) for label, n in networks.items()}


def figures(networks: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    labels = list(networks)
    caps = pd.DataFrame({lab: capacities_mw(n) for lab, n in networks.items()}).round(1)
    option, ds = charts.bars(labels, {c: caps.loc[c].tolist() for c in CARRIERS_MW}, "MW", stack=True, horizontal=False, category_name="co2 cap")
    mix = bundle.Figure(option, ds, title="Optimal capacity by CO2 cap",
                        caption="Power capacities per cap (electrolyser and fuel cell in MW electric). Gas gives way to "
                        "wind and solar, and hydrogen appears only for the last few percent.")
    costs = {lab: costs_by_carrier(n).sum(axis=1) / 1e6 for lab, n in networks.items()}
    cost_df = pd.DataFrame(costs).round(2)
    option, ds = charts.bars(labels, {c: cost_df.loc[c].tolist() for c in cost_df.index if cost_df.loc[c].abs().sum() > 0},
                             "MEUR/a", stack=True, horizontal=False, category_name="co2 cap")
    cost = bundle.Figure(option, ds, title="Annual system cost by technology",
                         caption="Annualised capital plus operating cost. The gas bar shrinks and the wind, solar and "
                         "storage bars grow; the total rises slowly until the cap approaches zero.")
    curves = {lab: n.buses_t.marginal_price["electricity"] for lab, n in networks.items()}
    option, ds = charts.duration_curves(curves, "EUR/MWh")
    option["yAxis"]["max"] = 400
    pdc = bundle.Figure(option, ds, title="Price duration curves",
                        caption="Prices sorted from high to low over the share of hours (axis clipped at 400 EUR/MWh; "
                        "scarcity hours reach the value of lost load). More zero-price hours and a few very high ones "
                        "as the cap tightens: that is how wind and solar recover their capital cost.")
    return {"capacity_mix_by_cap": mix, "cost_breakdown_by_cap": cost, "price_duration": pdc}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    networks = sweep()
    nums = numbers(networks)
    figs = figures(networks)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
