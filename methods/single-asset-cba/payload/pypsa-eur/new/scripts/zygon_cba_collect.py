# SPDX-License-Identifier: MIT
#
# CBA indicator computation — zygon methods payload `single-asset-cba`.
# Loads every solved variant network (config: zygon_cba.networks / labels),
# and for each PERTURBED variant computes the ENTSO-E CBA-guideline benefit
# indicators against the reference, direction-signed so that a POSITIVE
# value is a benefit of having the asset:
#
#   with/without resolution per variant v:
#     pint-*: with = v,   without = reference   (asset put in)
#     toot-*: with = ref, without = v           (asset taken out)
#
#   b1_sew  = objective(without) - objective(with)      [currency/a]
#             socio-economic welfare as the total-system-cost delta (the
#             Open-TYNDP B1 translation under inelastic demand). The
#             assessed asset must be capacity-fixed with zero counted capex,
#             so its own cost is excluded here and compared off-model.
#   b2_co2  = co2(without) - co2(with)                  [tCO2/a]
#             CO2 variation. Under a BINDING system CO2 cap this is ~0 by
#             construction — the cap, not the asset, sets emissions.
#   b3_res  = res(with) - res(without)                  [MWh/a]
#             RES integration as the change in weighted renewable GENERATOR
#             dispatch (storage/hydro storage units excluded by design).
#
# One long-format CSV per indicator (columns: network, direction, value),
# the reference included as a zero row so downstream comparison figures keep
# it. Any inconsistency (labels vs networks vs variants, unknown direction
# prefix, unknown indicator) aborts loudly — a silent partial collection is
# the dead-key failure class this harness exists to catch.

import json
import logging
from pathlib import Path

import pandas as pd
import pypsa

logger = logging.getLogger(__name__)

INDICATORS = ("b1_sew", "b2_co2", "b3_res")
RES_CARRIERS = {"solar", "solar rooftop", "solar-hsat", "onwind", "wind",
                "offwind", "offwind-ac", "offwind-dc", "offwind-float",
                "ror", "csp"}


def co2_emitted(n):
    """Annual CO2 emitted, tCO2. Sector-coupled networks account CO2 on the
    atmosphere store; power-only networks by primary-energy arithmetic."""
    if "co2 atmosphere" in n.stores.index:
        return float(n.stores_t.e["co2 atmosphere"].iloc[-1])
    em = n.carriers.co2_emissions
    em = em[em != 0]
    weights = n.snapshot_weightings.objective
    total = 0.0
    for carrier, factor in em.items():
        gens = n.generators[n.generators.carrier == carrier]
        if gens.empty:
            continue
        p = n.generators_t.p.reindex(columns=gens.index, fill_value=0.0)
        primary = p.div(gens.efficiency, axis=1).mul(weights, axis=0)
        total += float(primary.sum().sum()) * float(factor)
    return total


def res_dispatch(n):
    """Annual weighted renewable generator dispatch, MWh."""
    gens = n.generators[n.generators.carrier.isin(RES_CARRIERS)]
    if gens.empty:
        return 0.0
    p = n.generators_t.p.reindex(columns=gens.index, fill_value=0.0)
    weights = n.snapshot_weightings.objective
    return float(p.mul(weights, axis=0).sum().sum())


def direction_of(label, reference):
    if label == reference:
        return "ref"
    for prefix in ("pint-", "toot-"):
        if label.startswith(prefix):
            return prefix.rstrip("-")
    raise ValueError(f"variant '{label}' is neither the reference "
                     f"('{reference}') nor pint-*/toot-*")


if __name__ == "__main__":
    if snakemake.log:  # noqa: F821
        logging.basicConfig(filename=str(snakemake.log[0]),  # noqa: F821
                            level=logging.INFO)

    labels = [str(x) for x in snakemake.params.labels]  # noqa: F821
    reference = str(snakemake.params.reference)  # noqa: F821
    indicators = [str(x) for x in snakemake.params.indicators]  # noqa: F821
    networks = [str(p) for p in snakemake.input.networks]  # noqa: F821
    csvs = [str(p) for p in snakemake.output.csvs]  # noqa: F821

    if len(labels) != len(networks):
        raise ValueError(f"zygon_cba: {len(labels)} labels for "
                         f"{len(networks)} networks — must match 1:1")
    if len(set(labels)) != len(labels):
        raise ValueError(f"zygon_cba: labels not unique: {labels}")
    if reference not in labels:
        raise ValueError(f"zygon_cba: reference '{reference}' not in "
                         f"labels {labels}")
    unknown = [i for i in indicators if i not in INDICATORS]
    if unknown:
        raise ValueError(f"zygon_cba: unknown indicators {unknown} "
                         f"(built-in: {list(INDICATORS)})")
    directions = {label: direction_of(label, reference) for label in labels}
    if len(labels) < 2:
        raise ValueError("zygon_cba: need the reference plus at least one "
                         "perturbed variant")

    cost, co2, res = {}, {}, {}
    for label, path in zip(labels, networks):
        n = pypsa.Network(path)
        cost[label] = float(n.objective)
        co2[label] = co2_emitted(n)
        res[label] = res_dispatch(n)
        logger.info("variant '%s' (%s): objective %.6g, co2 %.6g t, "
                    "res %.6g MWh", label, directions[label], cost[label],
                    co2[label], res[label])

    def pair(label):
        """(with, without) labels for a perturbed variant."""
        if directions[label] == "pint":
            return label, reference
        return reference, label

    values = {i: {} for i in INDICATORS}
    for label in labels:
        if label == reference:
            for i in INDICATORS:
                values[i][label] = 0.0
            continue
        w, wo = pair(label)
        values["b1_sew"][label] = cost[wo] - cost[w]
        values["b2_co2"][label] = co2[wo] - co2[w]
        values["b3_res"][label] = res[w] - res[wo]

    # expand() preserves indicator order, so csvs[i] belongs to indicators[i]
    for indicator, csv_path in zip(indicators, csvs):
        frame = pd.DataFrame(
            {"network": labels,
             "direction": [directions[label] for label in labels],
             "value": [values[indicator][label] for label in labels]})
        frame.to_csv(csv_path, index=False)

    manifest = {"labels": labels, "reference": reference,
                "directions": directions, "networks": networks,
                "indicators": indicators,
                "objective": cost, "co2_t": co2, "res_mwh": res,
                "csvs": [str(Path(p)) for p in csvs]}
    Path(snakemake.output.manifest).write_text(  # noqa: F821
        json.dumps(manifest, indent=2) + "\n")
