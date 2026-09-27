# SPDX-License-Identifier: MIT
"""islanded-methanol: an off-grid plant that turns wind, solar and air into methanol.

No grid, no electricity demand: wind and solar feed an electrolyser and a direct air
capture unit, hydrogen and CO2 meet in a synthesis reactor, and a fixed annual
methanol demand has to be met from the product store. Everything is extendable, so
the optimiser sizes the generators, the battery, the electrolyser, the hydrogen and
methanol stores and the reactor against a year at six-hour resolution. The
objective divided by the methanol produced is its levelised cost.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, profiles, run  # noqa: E402

SLUG = "islanded-methanol"
TITLE = "Islanded methanol from wind, solar and air"

BASE = run.load_model("capacity-expansion-single-node")
EVERY_H = 6
METHANOL_DEMAND_MW = 10.0  # flat, 87.6 GWh a year
CO2_PER_MWH_MEOH = 0.25  # t
TECH = {
    "H2 Electrolysis": dict(overnight=700, life=25, fom=2.0, eta=0.70),
    "H2 Store": dict(overnight=10, life=30, fom=1.0),  # EUR/kWh
    "DAC": dict(overnight=6000, life=20, fom=4.0, el_per_t=2.0),  # EUR per kW electric
    "co2 store": dict(overnight=50, life=25, fom=1.0),  # EUR per t
    "methanolisation": dict(overnight=1200, life=25, fom=3.0, eta=0.80),  # per kW methanol out
    "methanol store": dict(overnight=2, life=30, fom=1.0),  # EUR/kWh
}
COMPONENTS = ["onwind", "solar", "battery", "H2 Electrolysis", "H2 Store", "DAC", "co2 store", "methanolisation", "methanol store"]


def _capex(t: str) -> float:
    s = TECH[t]
    return finance.capital_cost(s["overnight"], s["life"], fom_pct=s["fom"])


def build(*, demand_mw: float = METHANOL_DEMAND_MW) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.year_index(EVERY_H))
    n.snapshot_weightings.loc[:, :] = EVERY_H
    n.add("Carrier", ["AC", "H2", "co2", "methanol", "onwind", "solar", "battery", "H2 Electrolysis", "H2 Store", "DAC", "co2 store", "methanolisation", "methanol store"])
    n.add("Bus", ["electricity", "hydrogen", "co2", "methanol"], carrier=["AC", "H2", "co2", "methanol"])
    n.add("Generator", "onwind", bus="electricity", carrier="onwind", p_nom_extendable=True, capital_cost=BASE._capex("onwind"), p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", "solar", bus="electricity", carrier="solar", p_nom_extendable=True, capital_cost=BASE._capex("solar"), p_max_pu=profiles.solar(n.snapshots))
    b = BASE.TECH["battery"]
    n.add("StorageUnit", "battery", bus="electricity", carrier="battery", p_nom_extendable=True, capital_cost=BASE._capex("battery"),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
    n.add("Link", "H2 Electrolysis", bus0="electricity", bus1="hydrogen", carrier="H2 Electrolysis", p_nom_extendable=True,
          capital_cost=_capex("H2 Electrolysis"), efficiency=TECH["H2 Electrolysis"]["eta"])
    n.add("Store", "H2 Store", bus="hydrogen", carrier="H2 Store", e_nom_extendable=True, capital_cost=_capex("H2 Store"), e_cyclic=True)
    dac = TECH["DAC"]
    n.add("Link", "DAC", bus0="electricity", bus1="co2", carrier="DAC", p_nom_extendable=True, capital_cost=_capex("DAC"), efficiency=1 / dac["el_per_t"])
    n.add("Store", "co2 store", bus="co2", carrier="co2 store", e_nom_extendable=True, capital_cost=_capex("co2 store"), e_cyclic=True)
    me = TECH["methanolisation"]
    # p_nom is hydrogen input; the capital cost is quoted per kW of methanol output, so scale by efficiency
    n.add("Link", "methanolisation", bus0="hydrogen", bus1="methanol", bus2="co2", carrier="methanolisation", p_nom_extendable=True,
          capital_cost=_capex("methanolisation") * me["eta"], efficiency=me["eta"], efficiency2=-CO2_PER_MWH_MEOH * me["eta"])
    n.add("Store", "methanol store", bus="methanol", carrier="methanol store", e_nom_extendable=True, capital_cost=_capex("methanol store"), e_cyclic=True)
    n.add("Load", "methanol demand", bus="methanol", carrier="methanol", p_set=demand_mw)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def cost_breakdown(n: pypsa.Network) -> pd.Series:
    """Annualised cost per component (EUR/a)."""
    cr = finance.cost_recovery(n)
    return cr["cost"].reindex(COMPONENTS).fillna(0.0)


def numbers(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    meoh = float(n.loads.p_set["methanol demand"] * w.sum())
    costs = cost_breakdown(n)
    el_used = float(((n.links_t.p0["H2 Electrolysis"] + n.links_t.p0["DAC"]) * w).sum())
    avail = {c: float((n.generators_t.p_max_pu[c] * n.generators.p_nom_opt[c] * w).sum()) for c in ("onwind", "solar")}
    gen = {c: float((n.generators_t.p[c] * w).sum()) for c in ("onwind", "solar")}
    cap = n.statistics.optimal_capacity(comps=["Generator", "StorageUnit", "Link"]).groupby(level="carrier").sum()
    return {
        "levelised_cost_of_methanol_eur_mwh": float(n.objective / meoh),
        "cost_share_pct": {c: float(100 * costs[c] / costs.sum()) for c in COMPONENTS},
        "electricity_per_mwh_methanol": float(el_used / meoh),
        "methanol_gwh_a": meoh / 1e3,
        "capacity_mw": {c: float(cap.get(c, 0.0)) for c in ("onwind", "solar", "battery", "H2 Electrolysis", "DAC", "methanolisation")},
        "store_capacity": {"H2 Store_mwh": float(n.stores.e_nom_opt["H2 Store"]), "co2 store_t": float(n.stores.e_nom_opt["co2 store"]), "methanol store_mwh": float(n.stores.e_nom_opt["methanol store"])},
        "capacity_factor_pct": {"H2 Electrolysis": float(100 * (n.links_t.p0["H2 Electrolysis"] * w).sum() / (n.links.p_nom_opt["H2 Electrolysis"] * 8760)),
                                "methanolisation": float(100 * (n.links_t.p0["methanolisation"] * w).sum() / (n.links.p_nom_opt["methanolisation"] * 8760)),
                                "DAC": float(100 * (n.links_t.p0["DAC"] * w).sum() / (n.links.p_nom_opt["DAC"] * 8760)) if n.links.p_nom_opt["DAC"] > 1e-3 else None},
        "curtailment_pct": float(100 * (1 - sum(gen.values()) / sum(avail.values()))),
        "co2_captured_kt_a": float((n.links_t.p1["DAC"].abs() * w).sum() / 1e3),
        "total_cost_meur_a": float(n.objective / 1e6),
    }


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    cap = n.statistics.optimal_capacity(comps=["Generator", "StorageUnit", "Link"]).groupby(level="carrier").sum()
    techs = ["onwind", "solar", "battery", "H2 Electrolysis", "DAC", "methanolisation"]
    option, ds = charts.bars(techs, {"capacity": [round(float(cap.get(c, 0.0)), 1) for c in techs]}, "MW", category_name="technology")
    cb = bundle.Figure(option, ds, title="Optimal capacities",
                       caption="Wind and solar are three times the electrolyser, so that it runs much of the time on "
                       "whatever the weather gives; the reactor is sized well above the flat 10 MW demand, and the stores "
                       "decouple the steps.")
    st = pd.DataFrame({"H2 Store": n.stores_t.e["H2 Store"], "methanol store": n.stores_t.e["methanol store"],
                       "methanol output": -n.links_t.p1["methanolisation"] * 100}).round(1)
    option, ds = charts.time_series(st[["H2 Store", "methanol store"]], "MWh", slider=False)
    sf = bundle.Figure(option, ds, title="Hydrogen and methanol stores over the year",
                       caption="The hydrogen store buffers a few days of calm; the methanol store, far cheaper per MWh, "
                       "carries the seasons: it fills through the windy spring and empties over the calm late summer, "
                       "while the demand stays flat.")
    costs = cost_breakdown(n) / 1e6
    w = n.snapshot_weightings.generators
    meoh = float(n.loads.p_set["methanol demand"] * w.sum())
    per_mwh = (cost_breakdown(n) / meoh).round(2)
    comps = [c for c in COMPONENTS if per_mwh[c] > 0.05]
    option, ds = charts.bars(comps, {"EUR per MWh methanol": [float(per_mwh[c]) for c in comps]}, "EUR/MWh", horizontal=True, category_name="component")
    lc = bundle.Figure(option, ds, title="Levelised cost of methanol by component",
                       caption="Annualised cost of each component divided by the methanol produced; the sum is the "
                       "levelised cost. Wind and solar make up almost half, direct air capture a quarter, the "
                       "electrolyser an eighth; the stores are cheap.")
    return {"stores_over_year": sf, "lcom_breakdown": lc, "capacities": cb}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
