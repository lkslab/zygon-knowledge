# SPDX-License-Identifier: MIT
"""carbon-management: carbon as a tracked commodity across buses, with a net-zero
constraint on the atmosphere.

Electricity comes from wind, solar, gas and biomass. Gas plants emit to an atmosphere
bus; carbon capture on gas and on biomass, and direct air capture, move CO2 to a
captured bus, from where it is either sequestered or combined with electrolytic
hydrogen into methanol for a fuel demand. A Store on the atmosphere bus holds the
cumulative balance, and its end-of-period ceiling is the net-zero constraint; its bus
price is the CO2 shadow price.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, names, profiles, run  # noqa: E402

SLUG = "carbon-management"
TITLE = "Carbon management: capture, sequestration and synthetic fuel"

BASE = run.load_model("capacity-expansion-single-node")
MEAN_LOAD_MW = 100.0
FUEL_DEMAND_MW = 15.0  # methanol, flat
NET_TARGET_T = 0.0  # atmosphere balance at the end of the period, t CO2 (negative = net removal)
GAS_COST, BIOMASS_COST = 25.0, 35.0  # EUR/MWh thermal
EF_GAS, EF_BIO = 0.20, 0.30  # t CO2 per MWh thermal; biomass carbon is biogenic (uptake credited)
CAPTURE_RATE = 0.9
SEQ_COST = 15.0  # EUR/t
CO2_PER_MWH_MEOH = 0.25  # t CO2 needed per MWh of methanol
# overnight EUR/kW (of electric output for plants, of input for converters), life, FOM %
TECH = {
    "CCGT": dict(overnight=900, life=30, fom=2.0, eta=0.50),
    "CCGT CCS": dict(overnight=1800, life=30, fom=3.0, eta=0.44),
    "biomass": dict(overnight=2500, life=30, fom=3.0, eta=0.35),
    "BECCS": dict(overnight=4000, life=30, fom=4.0, eta=0.30),
    "DAC": dict(overnight=6000, life=20, fom=4.0, el_per_t=2.0),  # EUR per (t/h) capacity in kW-equivalents: see build
    "H2 Electrolysis": dict(overnight=700, life=25, fom=2.0, eta=0.70),
    "methanolisation": dict(overnight=1200, life=25, fom=3.0, eta=0.80),
}


def _capex(t: str) -> float:
    s = TECH[t]
    return finance.capital_cost(s["overnight"], s["life"], fom_pct=s["fom"])


def build(*, net_target_t: float = NET_TARGET_T, constrained: bool = True) -> pypsa.Network:
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "gas", "biomass", "co2", "co2 stored", "H2", "methanol", "onwind", "solar", "battery", "CCGT", "CCGT CCS",
                      "BECCS", "DAC", "H2 Electrolysis", "methanolisation", "co2 sequestration", "load shedding"])
    n.add("Bus", ["electricity", names.bus("gas"), names.bus("biomass"), "co2 atmosphere", "co2 captured", names.bus("co2 stored"), "hydrogen", names.bus("methanol")],
          carrier=["AC", "gas", "biomass", "co2", "co2", "co2 stored", "H2", "methanol"])
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, MEAN_LOAD_MW).loc[index])
    n.add("Load", "fuel demand", bus=names.bus("methanol"), carrier="methanol", p_set=FUEL_DEMAND_MW)
    n.add("Generator", names.gen("gas"), bus=names.bus("gas"), carrier="gas", p_nom=1e5, marginal_cost=GAS_COST)
    n.add("Generator", names.gen("biomass"), bus=names.bus("biomass"), carrier="biomass", p_nom=1e5, marginal_cost=BIOMASS_COST)
    n.add("Generator", names.gen("load shedding"), bus="electricity", carrier="load shedding", p_nom=1e5, marginal_cost=BASE.VOLL)
    n.add("Generator", names.gen("onwind"), bus="electricity", carrier="onwind", p_nom_extendable=True, capital_cost=BASE._capex("onwind"), p_max_pu=profiles.wind(year).loc[index])
    n.add("Generator", names.gen("solar"), bus="electricity", carrier="solar", p_nom_extendable=True, capital_cost=BASE._capex("solar"), p_max_pu=profiles.solar(year).loc[index])
    b = BASE.TECH["battery"]
    n.add("StorageUnit", names.unit("battery"), bus="electricity", carrier="battery", p_nom_extendable=True, capital_cost=BASE._capex("battery"),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
    # plants: Link p_nom is fuel input, so capital cost per MW input = cost per MW electric x efficiency
    for name, bus0, ef in (("CCGT", "gas", EF_GAS), ("biomass", "biomass", EF_BIO)):
        eta = TECH[name]["eta"]
        n.add("Link", names.link(name), bus0=names.bus(bus0), bus1="electricity", bus2="co2 atmosphere", carrier=name, p_nom_extendable=True,
              capital_cost=_capex(name) * eta, efficiency=eta, efficiency2=ef if name == "CCGT" else 0.0)
    eta = TECH["CCGT CCS"]["eta"]
    n.add("Link", names.link("CCGT CCS"), bus0=names.bus("gas"), bus1="electricity", bus2="co2 captured", bus3="co2 atmosphere", carrier="CCGT CCS",
          p_nom_extendable=True, capital_cost=_capex("CCGT CCS") * eta, efficiency=eta,
          efficiency2=CAPTURE_RATE * EF_GAS, efficiency3=(1 - CAPTURE_RATE) * EF_GAS)
    eta = TECH["BECCS"]["eta"]
    # biogenic carbon: the plant captures what the plant took from the air, so the captured
    # share is a removal from the atmosphere (negative efficiency = withdrawal from that bus)
    n.add("Link", names.link("BECCS"), bus0=names.bus("biomass"), bus1="electricity", bus2="co2 captured", bus3="co2 atmosphere", carrier="BECCS",
          p_nom_extendable=True, capital_cost=_capex("BECCS") * eta, efficiency=eta,
          efficiency2=CAPTURE_RATE * EF_BIO, efficiency3=-CAPTURE_RATE * EF_BIO)
    # DAC: electricity in, CO2 from atmosphere to captured; p_nom in MW electric, 1 t per el_per_t MWh
    dac = TECH["DAC"]
    n.add("Link", names.link("DAC"), bus0="electricity", bus1="co2 captured", bus2="co2 atmosphere", carrier="DAC", p_nom_extendable=True,
          capital_cost=_capex("DAC") / dac["el_per_t"], efficiency=1 / dac["el_per_t"], efficiency2=-1 / dac["el_per_t"])
    n.add("Link", names.link("co2 sequestration"), bus0="co2 captured", bus1=names.bus("co2 stored"), carrier="co2 sequestration", p_nom=1e5, marginal_cost=SEQ_COST)
    n.add("Store", names.unit("co2 stored"), bus=names.bus("co2 stored"), carrier="co2 stored", e_nom=1e9)
    n.add("Store", names.unit("co2 captured"), bus="co2 captured", carrier="co2", e_nom_extendable=True, capital_cost=finance.capital_cost(0.5, 30), e_cyclic=True)
    # the atmosphere: a store that may go negative (removals); its final content is the net balance
    e_max = pd.Series(1.0, index=index)
    if constrained:
        e_max.iloc[-1] = net_target_t / 1e9
    n.add("Store", names.unit("co2 atmosphere"), bus="co2 atmosphere", carrier="co2", e_nom=1e9, e_min_pu=-1.0, e_max_pu=e_max, e_initial=0.0)
    ely = TECH["H2 Electrolysis"]
    n.add("Link", names.link("H2 Electrolysis"), bus0="electricity", bus1="hydrogen", carrier="H2 Electrolysis", p_nom_extendable=True, capital_cost=_capex("H2 Electrolysis"), efficiency=ely["eta"])
    n.add("Store", names.unit("H2 Store"), bus="hydrogen", carrier="H2", e_nom_extendable=True, capital_cost=BASE._capex("H2 Store"), e_cyclic=True)
    me = TECH["methanolisation"]
    n.add("Link", names.link("methanolisation"), bus0="hydrogen", bus1=names.bus("methanol"), bus2="co2 captured", carrier="methanolisation", p_nom_extendable=True,
          capital_cost=_capex("methanolisation") * me["eta"], efficiency=me["eta"], efficiency2=-CO2_PER_MWH_MEOH * me["eta"])
    n.add("Store", names.unit("methanol"), bus=names.bus("methanol"), carrier="methanol", e_nom_extendable=True, capital_cost=finance.capital_cost(2, 30), e_cyclic=True)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def co2_flows_t(n: pypsa.Network) -> dict[str, float]:
    """Annual CO2 flows in t between the accounting buses (positive as named)."""
    w = n.snapshot_weightings.generators
    L = n.links_t

    def s(col: pd.Series) -> float:
        return float((col * w).sum())

    return {
        "gas -> atmosphere (CCGT)": s(-L.p2[names.link("CCGT")]),
        "gas -> atmosphere (CCS slip)": s(-L.p3[names.link("CCGT CCS")]),
        "gas -> captured (CCS)": s(-L.p2[names.link("CCGT CCS")]),
        "atmosphere -> captured (BECCS)": s(L.p3[names.link("BECCS")]),
        "atmosphere -> captured (DAC)": s(L.p2[names.link("DAC")]),
        "captured -> sequestered": s(L.p0[names.link("co2 sequestration")]),
        "captured -> methanol": s(L.p2[names.link("methanolisation")]),
    }


def capacities(n: pypsa.Network) -> pd.Series:
    """MW per technology: generators by carrier (the fuel supply generators excluded), links by name."""
    gens = n.generators.p_nom_opt.drop([names.gen(g) for g in ("gas", "biomass", "load shedding")])
    out = gens.groupby(n.generators.carrier).sum()
    out["battery"] = float(n.storage_units.p_nom_opt.sum())
    for lk in ("CCGT", "CCGT CCS", "biomass", "BECCS", "DAC", "H2 Electrolysis", "methanolisation"):
        out[lk] = float(n.links.p_nom_opt[names.link(lk)])
    return out


def numbers(n: pypsa.Network) -> dict:
    f = co2_flows_t(n)
    unconstrained = solve(build(constrained=False))
    w = n.snapshot_weightings.generators
    gross = f["gas -> atmosphere (CCGT)"] + f["gas -> atmosphere (CCS slip)"]
    removals = f["atmosphere -> captured (BECCS)"] + f["atmosphere -> captured (DAC)"]
    cap = capacities(n)
    price = n.buses_t.marginal_price
    return {
        "co2_kt": {"gross_emissions": gross / 1e3, "captured_from_gas": f["gas -> captured (CCS)"] / 1e3, "removed_by_beccs": f["atmosphere -> captured (BECCS)"] / 1e3,
                   "removed_by_dac": f["atmosphere -> captured (DAC)"] / 1e3, "sequestered": f["captured -> sequestered"] / 1e3,
                   "used_in_methanol": f["captured -> methanol"] / 1e3, "net_to_atmosphere": (gross - removals) / 1e3},
        "atmosphere_balance_end_t": float(n.stores_t.e[names.unit("co2 atmosphere")].iloc[-1]),
        "co2_shadow_price_eur_t": float(-price["co2 atmosphere"].mean()),
        "captured_co2_price_eur_t": float((price["co2 captured"] * w).sum() / w.sum()),
        "cost_of_net_zero_meur_a": float((n.objective - unconstrained.objective) / 1e6),
        "unconstrained_emissions_kt": float((co2_flows_t(unconstrained)["gas -> atmosphere (CCGT)"] + co2_flows_t(unconstrained)["gas -> atmosphere (CCS slip)"] - co2_flows_t(unconstrained)["atmosphere -> captured (BECCS)"] - co2_flows_t(unconstrained)["atmosphere -> captured (DAC)"]) / 1e3),
        "total_cost_meur_a": float(n.objective / 1e6),
        "capacity_mw": {c: float(cap.get(c, 0.0)) for c in ("onwind", "solar", "battery", "CCGT", "CCGT CCS", "biomass", "BECCS", "DAC", "H2 Electrolysis", "methanolisation")},
        "methanol_gwh_a": float(FUEL_DEMAND_MW * w.sum() / 1e3),
        "methanol_price_eur_mwh": float((price[names.bus("methanol")] * w).sum() / w.sum()),
        "electricity_price_eur_mwh": float((price["electricity"] * w).sum() / w.sum()),
        "load_shed_mwh": float((n.generators_t.p[names.gen("load shedding")] * w).sum()),
    }


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    f = co2_flows_t(n)
    edges = [
        ("gas combustion", "atmosphere", f["gas -> atmosphere (CCGT)"] + f["gas -> atmosphere (CCS slip)"]),
        ("gas combustion", "captured CO2", f["gas -> captured (CCS)"]),
        ("atmosphere", "captured CO2", f["atmosphere -> captured (BECCS)"] + f["atmosphere -> captured (DAC)"]),
        ("captured CO2", "sequestered", f["captured -> sequestered"]),
        ("captured CO2", "methanol", f["captured -> methanol"]),
    ]
    # node labels carry their tonnes, so the picture reads without hovering
    total = {}
    for a, b, v in edges:
        total[a] = total.get(a, 0.0) + v
        total[b] = total.get(b, 0.0)
    for a, b, v in edges:
        if b not in ("atmosphere", "captured CO2"):
            total[b] += v
    inflow_atm = sum(v for a, b, v in edges if b == "atmosphere")
    total["captured CO2"] = sum(v for a, b, v in edges if b == "captured CO2")
    label = {nm: f"{nm}\n{total[nm] / 1e3:.0f} kt" for nm in total}
    outflow_atm = sum(v for a, b, v in edges if a == "atmosphere")
    label["atmosphere"] = f"atmosphere\n{inflow_atm / 1e3:.0f} kt in\n{outflow_atm / 1e3:.0f} kt out"
    links = [{"source": label[a], "target": label[b], "value": round(v / 1e3, 2)} for a, b, v in edges if v > 1.0]
    nodes = [{"name": nm} for nm in dict.fromkeys([e for l in links for e in (l["source"], l["target"])])]
    option = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} kt"},
        "series": [{"type": "sankey", "data": nodes, "links": links, "emphasis": {"focus": "adjacency"},
                    "lineStyle": {"color": "gradient", "curveness": 0.5}, "nodeAlign": "justify", "label": {"fontSize": 12}}],
    }
    sk = bundle.Figure(option, {}, title="Annual CO2 flows (kt)",
                       caption="Carbon leaving the gas plants goes to the atmosphere or, through capture, to the captured "
                       "pool; BECCS and DAC pull from the atmosphere into the same pool. From there it is buried or "
                       "turned into methanol. The atmosphere's inflow minus its outflow is the net target.")
    cap = capacities(n)
    techs = [c for c in ("onwind", "solar", "battery", "CCGT", "CCGT CCS", "biomass", "BECCS", "DAC", "H2 Electrolysis", "methanolisation") if cap.get(c, 0) > 0.5]
    option, ds = charts.bars(techs, {"capacity": [round(float(cap[c]), 1) for c in techs]}, "MW (input for converters)", category_name="technology")
    cb = bundle.Figure(option, ds, title="Optimal capacity",
                       caption="Plants in MW of fuel input, DAC and the electrolyser in MW electric, methanolisation in MW "
                       "hydrogen. What the optimiser builds to hit net zero at least cost.")
    bal = pd.DataFrame({"atmosphere": n.stores_t.e[names.unit("co2 atmosphere")] / 1e3, "captured pool": n.stores_t.e[names.unit("co2 captured")] / 1e3}).round(2)
    option, ds = charts.time_series(bal, "kt CO2 (cumulative)", slider=False)
    tb = bundle.Figure(option, ds, title="Cumulative carbon balance",
                       caption="The atmosphere store rises when gas runs and falls when BECCS and DAC run; it must end "
                       "at the target. The captured pool buffers between capture and use.")
    return {"co2_sankey": sk, "capacity": cb, "carbon_balance": tb}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
