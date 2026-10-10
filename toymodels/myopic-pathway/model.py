# SPDX-License-Identifier: MIT
"""myopic-pathway: three planning horizons solved one after another, each seeing only
its own year, with the previous horizon's builds carried over and old plants retiring.

Existing coal and gas start the story; each decade adds new wind, solar, gas and
batteries at falling costs against a tightening CO2 cap and growing demand. Myopic
means no horizon anticipates the next: capacity built in 2030 is inherited, not
planned with 2050 in mind.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, names, profiles, run  # noqa: E402

SLUG = "myopic-pathway"
TITLE = "Myopic pathway with brownfield carry-over"

BASE = run.load_model("capacity-expansion-single-node")
HORIZONS = [2030, 2040, 2050]
MEAN_LOAD_MW = {2030: 100, 2040: 115, 2050: 130}
CAP_FRACTION = {2030: 0.6, 2040: 0.3, 2050: 0.15}  # of the unconstrained 2030 emissions
COST_DECLINE_PER_DECADE = {"onwind": 0.10, "solar": 0.15, "battery": 0.20, "CCGT": 0.0}
EXISTING = {  # name: carrier, MW, build year, lifetime, marginal cost
    "coal existing": ("coal", 100, 2000, 40, 30.0),
    "CCGT existing": ("CCGT", 50, 2015, 30, 60.0),
}
NEW = ["onwind", "solar", "CCGT", "battery"]
CARRIERS = ["coal", "CCGT", "onwind", "solar", "battery"]
CO2 = {"coal": 0.9, "CCGT": BASE.CO2_CCGT}


def _capex(tech: str, year: int) -> float:
    t = BASE.TECH[tech]
    decades = (year - 2030) / 10
    return finance.capital_cost(t["overnight"] * (1 - COST_DECLINE_PER_DECADE[tech]) ** decades, t["life"], fom_pct=t["fom"])


def build() -> pypsa.Network:
    """The network at the start of the pathway: existing plants, demand and profiles."""
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "load shedding", "onwind", "solar", "battery"])
    n.add("Carrier", "coal", co2_emissions=CO2["coal"])
    n.add("Carrier", "CCGT", co2_emissions=CO2["CCGT"])
    n.add("Bus", "electricity", carrier="AC")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, 1.0).loc[index])
    for name, (carrier, p_nom, by, life, mc) in EXISTING.items():
        n.add("Generator", name, bus="electricity", carrier=carrier, p_nom=p_nom, build_year=by, lifetime=life, marginal_cost=mc)
    n.add("Generator", names.gen("load shedding"), bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    n._profiles = {"wind": profiles.wind(year).loc[index], "solar": profiles.solar(year).loc[index]}  # noqa: SLF001
    return n


def add_horizon(n: pypsa.Network, year: int) -> None:
    """New extendable assets for `year`, load scaled, and old plants retired."""
    n.loads_t.p_set["demand"] = n.loads_t.p_set["demand"] / n.loads_t.p_set["demand"].mean() * MEAN_LOAD_MW[year]
    for comp in ("generators", "storage_units"):
        df = getattr(n, comp)
        if len(df):
            df["active"] = (df.build_year + df.lifetime > year) & (df.build_year <= year)
    life = {t: BASE.TECH[t]["life"] for t in NEW}
    n.add("Generator", f"onwind {year}", bus="electricity", carrier="onwind", p_nom_extendable=True, build_year=year,
          lifetime=life["onwind"], capital_cost=_capex("onwind", year), p_max_pu=n._profiles["wind"])
    n.add("Generator", f"solar {year}", bus="electricity", carrier="solar", p_nom_extendable=True, build_year=year,
          lifetime=life["solar"], capital_cost=_capex("solar", year), p_max_pu=n._profiles["solar"])
    n.add("Generator", f"CCGT {year}", bus="electricity", carrier="CCGT", p_nom_extendable=True, build_year=year,
          lifetime=life["CCGT"], capital_cost=_capex("CCGT", year), marginal_cost=BASE.TECH["CCGT"]["marginal_cost"])
    b = BASE.TECH["battery"]
    n.add("StorageUnit", f"battery {year}", bus="electricity", carrier="battery", p_nom_extendable=True, build_year=year,
          lifetime=life["battery"], capital_cost=_capex("battery", year), max_hours=b["max_hours"],
          efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)


def freeze(n: pypsa.Network) -> None:
    """After a solve: the optimised capacities become existing capacity."""
    for comp in ("generators", "storage_units"):
        df = getattr(n, comp)
        ext = df.p_nom_extendable
        df.loc[ext, "p_nom"] = df.loc[ext, "p_nom_opt"]
        df.loc[ext, "p_nom_extendable"] = False


def emissions_t(n: pypsa.Network) -> float:
    w = n.snapshot_weightings.generators
    act = n.generators[n.generators.active]
    return float(sum((n.generators_t.p[g] * w).sum() * CO2.get(act.carrier[g], 0.0) for g in act.index if g in n.generators_t.p))


def set_cap(n: pypsa.Network, tonnes: float) -> None:
    if "co2_limit" in n.global_constraints.index:
        n.global_constraints.loc["co2_limit", "constant"] = tonnes
    else:
        n.add("GlobalConstraint", "co2_limit", type="primary_energy", carrier_attribute="co2_emissions", sense="<=", constant=tonnes)


def pathway() -> tuple[pypsa.Network, dict[int, dict]]:
    """Solve the horizons in sequence; return the final network and a record per horizon."""
    n = build()
    # the reference: 2030 without a cap sets the absolute budget scale
    ref = build()
    add_horizon(ref, 2030)
    run.solve(ref)
    e2030 = emissions_t(ref)
    record: dict[int, dict] = {}
    for year in HORIZONS:
        add_horizon(n, year)
        set_cap(n, CAP_FRACTION[year] * e2030)
        run.solve(n)
        w = n.snapshot_weightings.generators
        act = n.generators[n.generators.active]
        cap = pd.Series(0.0, index=CARRIERS)
        new = pd.Series(0.0, index=CARRIERS)
        for g, row in act.iterrows():
            if row.carrier not in CARRIERS:
                continue
            mw = row.p_nom_opt if row.p_nom_extendable else row.p_nom
            cap[row.carrier] += mw
            if row.build_year == year:
                new[row.carrier] += mw
        for s, row in n.storage_units[n.storage_units.active].iterrows():
            mw = row.p_nom_opt if row.p_nom_extendable else row.p_nom
            cap["battery"] += mw
            if row.build_year == year:
                new["battery"] += mw
        supply = n.generators_t.p[act.index].mul(w, axis=0).sum().groupby(act.carrier).sum()
        demand = float((n.loads_t.p_set["demand"] * w).sum())
        capex_new = float(sum(row.p_nom_opt * row.capital_cost for _, row in act[act.p_nom_extendable].iterrows())
                          + sum(row.p_nom_opt * row.capital_cost for _, row in n.storage_units[n.storage_units.p_nom_extendable & n.storage_units.active].iterrows()))
        capex_old = float(sum(row.p_nom * row.capital_cost for _, row in act[~act.p_nom_extendable].iterrows())
                          + sum(row.p_nom * row.capital_cost for _, row in n.storage_units[~n.storage_units.p_nom_extendable & n.storage_units.active].iterrows()))
        opex = float(sum((n.generators_t.p[g] * w).sum() * act.marginal_cost[g] for g in act.index))
        record[year] = {
            "capacity_mw": cap.round(1).to_dict(),
            "new_build_mw": new.round(1).to_dict(),
            "emissions_kt": emissions_t(n) / 1e3,
            "cap_kt": CAP_FRACTION[year] * e2030 / 1e3,
            "co2_price_eur_t": float(-n.global_constraints.mu["co2_limit"]),
            "cost_meur_a": {"new capex": capex_new / 1e6, "existing capex": capex_old / 1e6, "opex": opex / 1e6},
            "vre_share_pct": float(100 * (supply.get("onwind", 0) + supply.get("solar", 0)) / demand),
            "mean_load_mw": MEAN_LOAD_MW[year],
            "load_shed_mwh": float((n.generators_t.p[names.gen("load shedding")] * w).sum()),
        }
        freeze(n)
    return n, record


def numbers(record: dict[int, dict]) -> dict:
    out = {str(y): r for y, r in record.items()}
    out["cumulative_new_build_mw"] = {c: float(sum(r["new_build_mw"][c] for r in record.values())) for c in CARRIERS}
    out["emission_reduction_2050_vs_2030_pct"] = float(100 * (1 - record[2050]["emissions_kt"] / max(record[2030]["emissions_kt"], 1e-9)))
    out["coal_retired_by"] = next((str(y) for y in HORIZONS if record[y]["capacity_mw"]["coal"] == 0), None)
    return out


def pathway_intuition(record: dict[int, dict]) -> bundle.Figure:
    """Each horizon's decision laid out: what it inherits, what it builds new, what retires
    before it. The new builds are all a myopic horizon decides; the rest is history."""
    years = [str(y) for y in HORIZONS]
    inherited, retired = [], []
    new: dict[str, list[float]] = {c: [] for c in CARRIERS}
    prev = {c: 0.0 for c in CARRIERS}
    for k, y in enumerate(HORIZONS):
        cap, built = record[y]["capacity_mw"], record[y]["new_build_mw"]
        kept = {c: cap[c] - built[c] for c in CARRIERS}
        inherited.append(round(sum(kept.values()), 1))
        retired.append(-round(sum(max(0.0, prev[c] - kept[c]) for c in CARRIERS), 1) if k else 0.0)
        for c in CARRIERS:
            new[c].append(round(built[c], 1))
        prev = cap
    data = {"already built: existing plants and earlier horizons": inherited, **{c: new[c] for c in CARRIERS if any(v > 0.05 for v in new[c])},
            "retired since the last horizon": retired}
    option, ds = charts.bars(years, data, "MW", stack=True, horizontal=False, category_name="horizon")
    for s in option["series"]:
        if s["name"] == "already built: existing plants and earlier horizons":
            s["itemStyle"] = {"color": "#c9ced8"}
        elif s["name"] == "retired since the last horizon":
            s["itemStyle"] = {"color": "#6b7280"}
    return bundle.Figure(
        option, ds, title="Each decade decides only its own builds",
        caption="Per horizon: the capacity it inherits (pale), what it builds new (coloured by technology) and what "
        "retired since the last one (below zero). A myopic horizon sees only its own year: 2040 replaces the retiring "
        "coal with new gas at a low CO2 price, and 2050, facing a far tighter cap, has to add most of the wind and solar at once.",
    )


def figures(record: dict[int, dict]) -> dict[str, bundle.Figure]:
    years = [str(y) for y in HORIZONS]
    option, ds = charts.bars(years, {c: [record[y]["capacity_mw"][c] for y in HORIZONS] for c in CARRIERS}, "MW", stack=True, horizontal=False, category_name="horizon")
    cap = bundle.Figure(option, ds, title="Installed capacity by horizon",
                        caption="Existing coal leaves at the end of its life; each horizon's wind, solar and battery "
                        "additions are inherited by the next. Gas stays as firm capacity even when it barely runs.")
    em = pd.DataFrame({"emissions": [record[y]["emissions_kt"] for y in HORIZONS], "cap": [record[y]["cap_kt"] for y in HORIZONS]},
                      index=pd.Index(HORIZONS, name="year")).round(1)
    option, ds = charts.xy_lines(em, "Horizon", "kt CO2 per year", symbols=True, x_extra={"min": 2025, "max": 2055, "interval": 10})
    option["series"][1]["lineStyle"] = {**option["series"][1].get("lineStyle", {}), "type": "dashed"}
    emis = bundle.Figure(option, ds, title="Emissions against the cap",
                         caption="Emissions sit on the cap in every horizon: the constraint binds, and its shadow "
                         "price is the CO2 price the horizon needs.")
    costs = {k: [round(record[y]["cost_meur_a"][k], 2) for y in HORIZONS] for k in ("new capex", "existing capex", "opex")}
    option, ds = charts.bars(years, costs, "MEUR/a", stack=True, horizontal=False, category_name="horizon")
    cost = bundle.Figure(option, ds, title="Annual cost by horizon",
                         caption="Capital cost of that horizon's new builds, the annuities still paid on inherited "
                         "assets, and fuel. Demand grows across the horizons, so the total rises.")
    return {"pathway_intuition": pathway_intuition(record), "capacity_by_horizon": cap, "emissions_path": emis, "cost_by_horizon": cost}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    _, record = pathway()
    nums = numbers(record)
    figs = figures(record)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
