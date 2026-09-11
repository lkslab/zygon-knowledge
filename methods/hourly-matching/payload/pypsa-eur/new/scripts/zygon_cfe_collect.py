# SPDX-License-Identifier: MIT
#
# Clean-procurement indicators — zygon methods payload `hourly-matching`
# (shared with `annual-matching`). Loads every solved variant (config:
# zygon_cfe.networks / labels, the reference label being the no-rule
# counterfactual) and writes one long-format CSV per indicator under
# results/zygon_cfe/:
#
#   procurement_cost  [EUR/MWh]  the consumer's all-in cost of electricity:
#                     annualised capex of the contracted assets + their
#                     marginal costs + grid imports priced at the zone's
#                     nodal price - excess sales at that price, per MWh of
#                     consumer demand. For the reference it is the grid-mix
#                     purchase cost.
#   premium           [EUR/MWh]  procurement_cost(v) - procurement_cost(ref):
#                     what the procurement rule costs the consumer.
#   system_cost_delta [EUR/a]    objective(v) - objective(ref): what the rule
#                     costs the system (the planner's reading).
#   cfe_score         ex post, three measures: `annual_available` = weighted
#                     available generation of the contracted plants (p_max_pu
#                     x p_nom_opt, the volumetric-PPA basis) / demand;
#                     `annual_dispatched` = weighted (dispatched generation +
#                     net storage - export) / demand; `hourly_min` = the worst
#                     snapshot's dispatched share (the 24/7 basis).
#   procured_capacity per contracted asset: MW (generators, links) or MWh (stores).
#   scope2_emissions  [tCO2/a]   grid imports x the zone's hourly emission
#                     intensity of supply (from the solved dispatch).
#   grid_exchange     import_share / export_share of consumer demand.
# Plus results/zygon_cfe/grid_cfe_factor.csv: the reference zone's hourly
# carbon-free share of supply — the CFE_t series a second, import-crediting
# pass reads through zygon_cfe.grid_cfe.series (Riepin: 2 passes converge).
# Any inconsistency aborts loudly; a silent partial collection is the
# dead-key failure class this harness exists to catch.

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
from pypsa.descriptors import get_switchable_as_dense as get_as_dense

logger = logging.getLogger(__name__)

INDICATORS = ("procurement_cost", "premium", "system_cost_delta", "cfe_score",
              "procured_capacity", "scope2_emissions", "grid_exchange")
GRID_CARRIERS = ("zcfe import", "zcfe export")
SLACK_CARRIERS = ("load",)


def zone_supply_and_emissions(n, zone):
    """Hourly supply into the zone bus (MW) and the emissions behind it (t/h)
    from the solved dispatch: generators at the bus (co2 via carrier
    intensity / efficiency) and links delivering into it (co2 via their
    co2-atmosphere leg, sign: p_i = -eff_i p0, so emissions = -p2 where bus2
    is the atmosphere)."""
    w = n.snapshot_weightings.objective
    supply = pd.Series(0.0, index=n.snapshots)
    emis = pd.Series(0.0, index=n.snapshots)
    gens = n.generators[(n.generators.bus == zone)
                        & ~n.generators.index.str.startswith("zcfe:")]
    if not gens.empty:
        p = n.generators_t.p.reindex(columns=gens.index, fill_value=0.0).clip(lower=0)
        supply += p.sum(axis=1)
        co2 = gens.carrier.map(n.carriers.co2_emissions).fillna(0.0)
        emis += (p.div(gens.efficiency.replace(0, np.nan), axis=1).fillna(0.0)
                 .mul(co2, axis=1)).sum(axis=1)
    links = n.links[(n.links.bus1 == zone) & ~n.links.carrier.isin(GRID_CARRIERS)
                    & ~n.links.index.str.startswith("zcfe:")]
    if not links.empty:
        p1 = -n.links_t.p1.reindex(columns=links.index, fill_value=0.0)
        supply += p1.clip(lower=0).sum(axis=1)
        for leg in ("bus2", "bus3", "bus4"):
            if leg not in links.columns:
                continue
            atm = links[links[leg] == "co2 atmosphere"].index
            if len(atm):
                col = "p" + leg[-1]
                emis += (-n.links_t[col].reindex(columns=atm, fill_value=0.0)).clip(lower=0).sum(axis=1)
    sus = n.storage_units[n.storage_units.bus == zone]
    if not sus.empty:
        supply += n.storage_units_t.p.reindex(columns=sus.index, fill_value=0.0).clip(lower=0).sum(axis=1)
    return supply, emis, w


def collect_variant(n, cfg):
    name = str(cfg["consumer"]["name"])
    zone = str(cfg["consumer"]["bus"])
    pre = f"zcfe:{name}:"
    bus, load, imp, exp = pre + "bus", pre + "load", pre + "import", pre + "export"
    for x, df in ((bus, n.buses), (load, n.loads), (imp, n.links), (exp, n.links)):
        if x not in df.index:
            raise KeyError(f"'{x}' missing — not a zygon_cfe variant network")
    w = n.snapshot_weightings.objective
    price = n.buses_t.marginal_price[zone]
    demand_t = get_as_dense(n, "Load", "p_set")[load]
    demand = float((w * demand_t).sum())
    if demand <= 0:
        raise ValueError(f"consumer '{name}' has zero demand")
    import_t = n.links_t.p0[imp].clip(lower=0)
    export_t = n.links_t.p0[exp].clip(lower=0)

    gens = n.generators[n.generators.index.str.startswith(pre)
                        & ~n.generators.carrier.isin(SLACK_CARRIERS)]
    stores = n.stores[n.stores.index.str.startswith(pre)]
    links = n.links[n.links.index.str.startswith(pre) & ~n.links.carrier.isin(GRID_CARRIERS)]
    dischargers = links[links.bus1 == bus]
    chargers = links[links.bus0 == bus]
    gen_t = n.generators_t.p.reindex(columns=gens.index, fill_value=0.0).sum(axis=1)
    # net storage contribution: delivered minus drawn (a pass-through earns nothing)
    dis_t = ((-n.links_t.p1.reindex(columns=dischargers.index, fill_value=0.0)).clip(lower=0).sum(axis=1)
             - n.links_t.p0.reindex(columns=chargers.index, fill_value=0.0).clip(lower=0).sum(axis=1))

    capex = float((gens.capital_cost * gens.p_nom_opt).sum()
                  + (stores.capital_cost * stores.e_nom_opt).sum()
                  + (links.capital_cost * links.p_nom_opt).sum())
    opex = float((n.generators_t.p.reindex(columns=gens.index, fill_value=0.0)
                  .mul(w, axis=0).mul(gens.marginal_cost, axis=1)).sum().sum()
                 + (n.links_t.p0.reindex(columns=links.index, fill_value=0.0)
                    .mul(w, axis=0).mul(links.marginal_cost, axis=1)).sum().sum())
    import_cost = float((w * price * import_t).sum())
    export_rev = float((w * price * export_t).sum())
    cost = (capex + opex + import_cost - export_rev) / demand

    matched = w * (gen_t + dis_t - export_t)
    annual_score = float(matched.sum() / demand)
    cf = n.generators_t.p_max_pu.reindex(columns=gens.index)
    avail_t = pd.Series(0.0, index=n.snapshots)
    for g in gens.index:
        if g in cf.columns and cf[g].notna().all():
            avail_t += cf[g] * float(gens.at[g, "p_nom_opt"])
        else:
            avail_t += n.generators_t.p.get(g, pd.Series(0.0, index=n.snapshots))
    annual_available = float((w * avail_t).sum() / demand)
    with np.errstate(divide="ignore", invalid="ignore"):
        hourly = ((gen_t + dis_t - export_t) / demand_t.replace(0, np.nan)).dropna()
    hourly_min = float(hourly.min()) if len(hourly) else float("nan")

    supply, emis, _ = zone_supply_and_emissions(n, zone)
    intensity = (emis / supply.replace(0, np.nan)).fillna(0.0)
    scope2 = float((w * import_t * intensity).sum())
    cfe_factor = clean_share(n, zone, supply)

    capacity = pd.concat([
        pd.Series(gens.p_nom_opt.values, index=gens.index),
        pd.Series(links.p_nom_opt.values, index=links.index),
        pd.Series(stores.e_nom_opt.values, index=stores.index),
    ])
    return {
        "objective": float(n.objective),
        "demand_mwh": demand,
        "procurement_cost": cost,
        "capex": capex, "opex": opex, "import_cost": import_cost, "export_rev": export_rev,
        "cfe_score": {"annual_available": annual_available, "annual_dispatched": annual_score,
                      "hourly_min": hourly_min},
        "procured_capacity": capacity,
        "scope2_emissions": scope2,
        "grid_exchange": {"import_share": float((w * import_t).sum() / demand),
                          "export_share": float((w * export_t).sum() / demand)},
        "grid_cfe_factor": cfe_factor,
    }


def clean_share(n, zone, supply):
    """Share of the zone's hourly supply delivered by non-emitting components."""
    clean = pd.Series(0.0, index=n.snapshots)
    gens = n.generators[(n.generators.bus == zone)
                        & ~n.generators.index.str.startswith("zcfe:")]
    co2 = gens.carrier.map(n.carriers.co2_emissions).fillna(0.0)
    cg = gens.index[co2 == 0]
    if len(cg):
        clean += n.generators_t.p.reindex(columns=cg, fill_value=0.0).clip(lower=0).sum(axis=1)
    links = n.links[(n.links.bus1 == zone) & ~n.links.carrier.isin(GRID_CARRIERS)
                    & ~n.links.index.str.startswith("zcfe:")]
    emitting = pd.Series(False, index=links.index)
    for leg in ("bus2", "bus3", "bus4"):
        if leg in links.columns:
            emitting |= links[leg] == "co2 atmosphere"
    cl = links.index[~emitting]
    if len(cl):
        clean += (-n.links_t.p1.reindex(columns=cl, fill_value=0.0)).clip(lower=0).sum(axis=1)
    sus = n.storage_units[n.storage_units.bus == zone]
    if not sus.empty:
        clean += n.storage_units_t.p.reindex(columns=sus.index, fill_value=0.0).clip(lower=0).sum(axis=1)
    return (clean / supply.replace(0, np.nan)).clip(0, 1).fillna(1.0)


def frame(rows, columns):
    return pd.DataFrame(rows, columns=columns)


if __name__ == "__main__":
    if snakemake.log:  # noqa: F821
        logging.basicConfig(filename=str(snakemake.log[0]),  # noqa: F821
                            level=logging.INFO)

    cfg = dict(snakemake.params.cfe)  # noqa: F821
    labels = [str(x) for x in snakemake.params.labels]  # noqa: F821
    reference = str(snakemake.params.reference)  # noqa: F821
    indicators = [str(x) for x in snakemake.params.indicators]  # noqa: F821
    networks = [str(p) for p in snakemake.input.networks]  # noqa: F821
    baseline = [str(p) for p in snakemake.input.get("baseline", [])]  # noqa: F821
    csvs = [str(p) for p in snakemake.output.csvs]  # noqa: F821

    if len(labels) != len(networks):
        raise ValueError(f"zygon_cfe: {len(labels)} labels for {len(networks)} "
                         "networks — must match 1:1")
    if len(set(labels)) != len(labels):
        raise ValueError(f"zygon_cfe: labels not unique: {labels}")
    if reference not in labels:
        raise ValueError(f"zygon_cfe: reference '{reference}' not in labels {labels}")
    unknown = [i for i in indicators if i not in INDICATORS]
    if unknown:
        raise ValueError(f"zygon_cfe: unknown indicators {unknown} (built-in: {list(INDICATORS)})")

    res = {}
    for label, path in zip(labels, networks):
        n = pypsa.Network(path)
        res[label] = collect_variant(n, cfg)
        logger.info("variant '%s': cost %.2f EUR/MWh, CFE available %.3f dispatched %.3f (min %.3f), objective %.6g",
                    label, res[label]["procurement_cost"], res[label]["cfe_score"]["annual_available"],
                    res[label]["cfe_score"]["annual_dispatched"], res[label]["cfe_score"]["hourly_min"],
                    res[label]["objective"])
    ref = res[reference]
    base_objective = None
    if baseline:
        base_objective = float(pypsa.Network(baseline[0]).objective)

    tables = {
        "procurement_cost": frame([(l, r["procurement_cost"]) for l, r in res.items()],
                                  ["network", "value"]),
        "premium": frame([(l, r["procurement_cost"] - ref["procurement_cost"])
                          for l, r in res.items()], ["network", "value"]),
        "system_cost_delta": frame([(l, r["objective"] - ref["objective"])
                                    for l, r in res.items()], ["network", "value"]),
        "cfe_score": frame([(l, k, v) for l, r in res.items() for k, v in r["cfe_score"].items()],
                           ["network", "measure", "value"]),
        "procured_capacity": frame([(l, a, float(v)) for l, r in res.items()
                                    for a, v in r["procured_capacity"].items()],
                                   ["network", "asset", "value"]),
        "scope2_emissions": frame([(l, r["scope2_emissions"]) for l, r in res.items()],
                                  ["network", "value"]),
        "grid_exchange": frame([(l, k, v) for l, r in res.items() for k, v in r["grid_exchange"].items()],
                               ["network", "measure", "value"]),
    }
    # expand() preserves indicator order, so csvs[i] belongs to indicators[i]
    for indicator, csv_path in zip(indicators, csvs):
        tables[indicator].to_csv(csv_path, index=False)

    ref["grid_cfe_factor"].rename("cfe").to_csv(snakemake.output.grid_cfe)  # noqa: F821

    manifest = {"labels": labels, "reference": reference, "networks": networks,
                "baseline": baseline, "baseline_objective": base_objective,
                "indicators": indicators,
                "objective": {l: r["objective"] for l, r in res.items()},
                "demand_mwh": {l: r["demand_mwh"] for l, r in res.items()},
                "cost_breakdown": {l: {k: r[k] for k in ("capex", "opex", "import_cost", "export_rev")}
                                   for l, r in res.items()},
                "csvs": [str(Path(p)) for p in csvs]}
    Path(snakemake.output.manifest).write_text(  # noqa: F821
        json.dumps(manifest, indent=2) + "\n")
