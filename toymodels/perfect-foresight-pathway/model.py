# SPDX-License-Identifier: MIT
"""perfect-foresight-pathway: the myopic pathway's three horizons solved as one problem.

Same existing plants, candidate technologies, cost declines, load growth and CO2 caps
as myopic-pathway, but 2030, 2040 and 2050 are investment periods of a single
optimisation: every build decision knows what the later caps and costs will be, and
an asset's capital cost is paid in every period it is alive. The committed myopic
results are read back for the comparison.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402

SLUG = "perfect-foresight-pathway"
TITLE = "Perfect-foresight pathway vs myopic"

MYOPIC = run.load_model("myopic-pathway")
BASE = MYOPIC.BASE
HORIZONS = MYOPIC.HORIZONS
YEARS_PER_PERIOD = 10
CARRIERS = MYOPIC.CARRIERS
NEW = MYOPIC.NEW
CO2 = MYOPIC.CO2


def build(*, e2030: float) -> pypsa.Network:
    """One network with MultiIndex snapshots (period, timestep) over the two fortnights."""
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(pd.MultiIndex.from_product([HORIZONS, index], names=["period", "timestep"]))
    n.investment_periods = HORIZONS
    n.investment_period_weightings["years"] = YEARS_PER_PERIOD
    n.investment_period_weightings["objective"] = YEARS_PER_PERIOD  # undiscounted decade totals
    # not `.loc[:, :] = weight`: on MultiIndex snapshots that assignment makes PyPSA 1.3
    # lose the snapshot dimension of every time-varying attribute (the solve then fails
    # with "'snapshot' is not a valid dimension" in the storage spillage variables)
    n.snapshot_weightings = n.snapshot_weightings * 0 + weight
    n.add("Carrier", ["AC", "load shedding", "onwind", "solar", "battery"])
    n.add("Carrier", "coal", co2_emissions=CO2["coal"])
    n.add("Carrier", "CCGT", co2_emissions=CO2["CCGT"])
    n.add("Bus", "electricity", carrier="AC")
    base_load = profiles.annual_load(year, 1.0).loc[index]
    load = pd.concat({h: base_load / base_load.mean() * MYOPIC.MEAN_LOAD_MW[h] for h in HORIZONS})
    load.index.names = ["period", "timestep"]
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=load)
    for name, (carrier, p_nom, by, life, mc) in MYOPIC.EXISTING.items():
        n.add("Generator", name, bus="electricity", carrier=carrier, p_nom=p_nom, build_year=by, lifetime=life, marginal_cost=mc)
    n.add("Generator", names.gen("load shedding"), bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    wind = pd.concat({h: profiles.wind(year).loc[index] for h in HORIZONS})
    solar = pd.concat({h: profiles.solar(year).loc[index] for h in HORIZONS})
    for s in (wind, solar):
        s.index.names = ["period", "timestep"]
    life = {t: BASE.TECH[t]["life"] for t in NEW}
    for h in HORIZONS:
        n.add("Generator", f"onwind {h}", bus="electricity", carrier="onwind", p_nom_extendable=True, build_year=h,
              lifetime=life["onwind"], capital_cost=MYOPIC._capex("onwind", h), p_max_pu=wind)
        n.add("Generator", f"solar {h}", bus="electricity", carrier="solar", p_nom_extendable=True, build_year=h,
              lifetime=life["solar"], capital_cost=MYOPIC._capex("solar", h), p_max_pu=solar)
        n.add("Generator", f"CCGT {h}", bus="electricity", carrier="CCGT", p_nom_extendable=True, build_year=h,
              lifetime=life["CCGT"], capital_cost=MYOPIC._capex("CCGT", h), marginal_cost=BASE.TECH["CCGT"]["marginal_cost"])
        b = BASE.TECH["battery"]
        n.add("StorageUnit", f"battery {h}", bus="electricity", carrier="battery", p_nom_extendable=True, build_year=h,
              lifetime=life["battery"], capital_cost=MYOPIC._capex("battery", h), max_hours=b["max_hours"],
              efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True)
        # a per-period constraint sums emissions over the period's `years` weighting, so
        # the constant is a decade budget, not an annual one
        n.add("GlobalConstraint", f"co2_limit_{h}", type="primary_energy", carrier_attribute="co2_emissions",
              sense="<=", constant=MYOPIC.CAP_FRACTION[h] * e2030 * YEARS_PER_PERIOD, investment_period=h)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n, multi_investment_periods=True)


def reference_e2030() -> float:
    """The unconstrained 2030 emissions the caps are fractions of, the same way myopic-pathway gets them."""
    ref = MYOPIC.build()
    MYOPIC.add_horizon(ref, 2030)
    run.solve(ref)
    return MYOPIC.emissions_t(ref)


def active(n: pypsa.Network, comp: str, h: int) -> pd.DataFrame:
    df = getattr(n, comp)
    return df[(df.build_year <= h) & (df.build_year + df.lifetime > h)]


def record(n: pypsa.Network, e2030: float) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for h in HORIZONS:
        w = n.snapshot_weightings.generators.loc[h]
        gens = active(n, "generators", h)
        sus = active(n, "storage_units", h)
        cap = pd.Series(0.0, index=CARRIERS)
        new = pd.Series(0.0, index=CARRIERS)
        for g, row in gens.iterrows():
            if row.carrier not in CARRIERS:
                continue
            mw = row.p_nom_opt if row.p_nom_extendable else row.p_nom
            cap[row.carrier] += mw
            if row.build_year == h:
                new[row.carrier] += mw
        for s, row in sus.iterrows():
            mw = row.p_nom_opt if row.p_nom_extendable else row.p_nom
            cap["battery"] += mw
            if row.build_year == h:
                new["battery"] += mw
        p = n.generators_t.p.loc[h, gens.index]
        supply = p.mul(w, axis=0).sum().groupby(gens.carrier).sum()
        demand = float((n.loads_t.p_set.loc[h, "demand"] * w).sum())
        emissions = float(sum(supply.get(c, 0.0) * CO2.get(c, 0.0) for c in supply.index))
        capex_new = float(sum(r.p_nom_opt * r.capital_cost for _, r in gens[gens.p_nom_extendable & (gens.build_year == h)].iterrows())
                          + sum(r.p_nom_opt * r.capital_cost for _, r in sus[sus.build_year == h].iterrows()))
        capex_old = float(sum(r.p_nom_opt * r.capital_cost for _, r in gens[gens.p_nom_extendable & (gens.build_year < h)].iterrows())
                          + sum(r.p_nom_opt * r.capital_cost for _, r in sus[sus.build_year < h].iterrows()))
        opex = float(sum((p[g] * w).sum() * gens.marginal_cost[g] for g in gens.index))
        out[h] = {
            "capacity_mw": cap.round(1).to_dict(),
            "new_build_mw": new.round(1).to_dict(),
            "emissions_kt": emissions / 1e3,
            "co2_price_eur_t": float(-n.global_constraints.mu[f"co2_limit_{h}"]),
            "cap_kt": MYOPIC.CAP_FRACTION[h] * e2030 / 1e3,
            "cost_meur_a": {"new capex": capex_new / 1e6, "existing capex": capex_old / 1e6, "opex": opex / 1e6},
            "vre_share_pct": float(100 * (supply.get("onwind", 0) + supply.get("solar", 0)) / demand),
        }
    return out


def myopic_record() -> dict[int, dict]:
    doc = yaml.safe_load((Path(__file__).resolve().parents[1] / "myopic-pathway" / "results.yaml").read_text())
    return {h: doc["numbers"][str(h)] for h in HORIZONS}


def _total(rec: dict[int, dict]) -> float:
    return float(sum(sum(rec[h]["cost_meur_a"].values()) * YEARS_PER_PERIOD for h in HORIZONS))


def numbers(n: pypsa.Network, rec: dict[int, dict]) -> dict:
    my = myopic_record()
    total_pf, total_my = _total(rec), _total(my)
    earlier = {c: [h for h in HORIZONS if rec[h]["new_build_mw"][c] > my[h]["new_build_mw"][c] + 1] for c in CARRIERS}
    return {
        "perfect_foresight": {str(h): rec[h] for h in HORIZONS},
        "myopic_from_results": {str(h): {k: my[h][k] for k in ("capacity_mw", "new_build_mw", "emissions_kt", "co2_price_eur_t", "cost_meur_a")} for h in HORIZONS},
        "pathway_cost_meur": {"perfect_foresight": total_pf, "myopic": total_my},
        "foresight_gap_pct": float(100 * (total_my - total_pf) / total_pf),
        "objective_meur": float(n.objective / 1e6),
        "builds_more_than_myopic_in": {c: [str(h) for h in hs] for c, hs in earlier.items()},
        "cumulative_new_build_mw": {"perfect_foresight": {c: float(sum(rec[h]["new_build_mw"][c] for h in HORIZONS)) for c in CARRIERS},
                                    "myopic": {c: float(sum(my[h]["new_build_mw"][c] for h in HORIZONS)) for c in CARRIERS}},
    }


def figures(n: pypsa.Network, rec: dict[int, dict]) -> dict[str, bundle.Figure]:
    my = myopic_record()
    labels = [f"{h} {k}" for h in HORIZONS for k in ("perfect", "myopic")]
    data = {c: [round((rec if k == "perfect" else my)[h]["capacity_mw"][c], 1) for h in HORIZONS for k in ("perfect", "myopic")] for c in CARRIERS}
    option, ds = charts.bars(labels, data, "MW", stack=True, horizontal=False, category_name="horizon and foresight")
    cap = bundle.Figure(option, ds, title="Installed capacity per horizon, perfect foresight beside myopic",
                        caption="Same horizons, same caps and costs. With foresight the plan front-loads wind and "
                        "solar because it knows the 2050 cap and the cheaper later builds are coming.")
    years = [str(h) for h in HORIZONS]
    costs = {"perfect foresight": [round(sum(rec[h]["cost_meur_a"].values()), 2) for h in HORIZONS],
             "myopic": [round(sum(my[h]["cost_meur_a"].values()), 2) for h in HORIZONS]}
    option, ds = charts.bars(years, costs, "MEUR/a", category_name="horizon")
    cost = bundle.Figure(option, ds, title="Annual cost per horizon",
                         caption="Perfect foresight may spend more early and less late; the pathway total, decade by "
                         "decade, is what the foresight gap number compares.")
    em = pd.DataFrame({"perfect foresight": [rec[h]["emissions_kt"] for h in HORIZONS], "myopic": [my[h]["emissions_kt"] for h in HORIZONS],
                       "cap": [my[h]["cap_kt"] for h in HORIZONS]}, index=pd.Index(HORIZONS, name="year")).round(1)
    option, ds = charts.xy_lines(em, "Horizon", "kt CO2 per year", symbols=True, x_extra={"min": 2025, "max": 2055, "interval": 10})
    option["series"][2]["lineStyle"] = {**option["series"][2].get("lineStyle", {}), "type": "dashed"}
    emis = bundle.Figure(option, ds, title="Emissions against the cap, both foresights",
                         caption="Both plans sit on the cap where it binds; foresight can undershoot an early cap when "
                         "building early is cheaper than building later.")
    return {"capacity_perfect_vs_myopic": cap, "cost_per_horizon": cost, "emissions_path": emis}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    e2030 = reference_e2030()
    n = solve(build(e2030=e2030))
    rec = record(n, e2030)
    nums = numbers(n, rec)
    figs = figures(n, rec)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
