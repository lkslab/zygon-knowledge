# SPDX-License-Identifier: MIT
#
# Declarative scenario-variant builder — zygon methods payload
# `multi-scenario` (pypsa-earth tree). Reads the settled prepared
# electricity network, applies the ordered operation list for ONE variant
# (config: zygon_scenarios.variants.<name>), writes the variant prepared
# network for solve_scenario_network.
#
# Operation schema (kept deliberately small):
#   component: pypsa component list attr (generators, links, lines,
#              storage_units, stores, loads, buses, global_constraints,
#              carriers)
#   where:     {column-or-'index': value | [values]} — conjunctive selection
#   attr:      the static column to modify
#   op:        set | scale | add
#   value:     scalar (set may assign non-numeric, scale/add coerce float)
#
# An EMPTY operation list is an untouched reference copy. An operation whose
# selection matches nothing is a HARD ERROR: a silently unchanged variant is
# the dead-key failure class the zygon harness exists to catch.

import logging

import pandas as pd
import pypsa

logger = logging.getLogger(__name__)

COMPONENTS = {"generators", "links", "lines", "storage_units", "stores",
              "loads", "buses", "transformers", "global_constraints",
              "carriers"}
OPS = {"set", "scale", "add"}


def select(df, where, addr):
    mask = pd.Series(True, index=df.index)
    for column, wanted in (where or {}).items():
        values = wanted if isinstance(wanted, list) else [wanted]
        if column == "index":
            mask &= df.index.isin(values)
        else:
            if column not in df.columns:
                raise KeyError(f"{addr}: where-column '{column}' not a "
                               f"static attribute (have: "
                               f"{sorted(df.columns)[:20]}...)")
            mask &= df[column].isin(values)
    return mask


def apply_operation(n, spec, addr):
    component = spec.get("component")
    attr = spec.get("attr")
    op = spec.get("op")
    if component not in COMPONENTS:
        raise ValueError(f"{addr}: component must be one of "
                         f"{sorted(COMPONENTS)}, got {component!r}")
    if op not in OPS:
        raise ValueError(f"{addr}: op must be one of {sorted(OPS)}, "
                         f"got {op!r}")
    df = getattr(n, component)
    if attr not in df.columns:
        raise KeyError(f"{addr}: '{attr}' not a static attribute of "
                       f"{component}")
    mask = select(df, spec.get("where"), addr)
    if not mask.any():
        raise ValueError(f"{addr}: selection {spec.get('where')!r} matched "
                         f"no {component} rows — a no-op variant is a hard "
                         "error")
    value = spec.get("value")
    if op == "set":
        df.loc[mask, attr] = value
    elif op == "scale":
        df.loc[mask, attr] = df.loc[mask, attr].astype(float) * float(value)
    elif op == "add":
        df.loc[mask, attr] = df.loc[mask, attr].astype(float) + float(value)
    logger.info("%s: %s %s.%s on %d row(s) with value %s",
                addr, op, component, attr, int(mask.sum()), value)
    return int(mask.sum())


if __name__ == "__main__":
    if snakemake.log:  # noqa: F821
        logging.basicConfig(filename=str(snakemake.log[0]),  # noqa: F821
                            level=logging.INFO)

    zscen = snakemake.wildcards.zscen  # noqa: F821
    operations = list(snakemake.params.variant)  # noqa: F821

    n = pypsa.Network(snakemake.input.network)  # noqa: F821
    touched = 0
    for i, spec in enumerate(operations):
        touched += apply_operation(n, dict(spec),
                                   f"variant '{zscen}' op[{i}]")
    logger.info("variant '%s': %d operation(s), %d row(s) touched",
                zscen, len(operations), touched)

    n.meta = dict(n.meta, zygon_scenario={"name": str(zscen),
                                          "operations": operations})
    n.export_to_netcdf(snakemake.output[0])  # noqa: F821
