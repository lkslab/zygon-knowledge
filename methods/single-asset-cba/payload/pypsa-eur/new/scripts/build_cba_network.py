# SPDX-License-Identifier: MIT
#
# Declarative single-asset perturbation — zygon methods payload
# `single-asset-cba`. Reads the settled prepared network, applies the ordered
# operation list for ONE variant (config: zygon_cba.variants.<label>), writes
# the variant prepared network for solve_cba_network.
#
# Direction is mechanical, carried by the label: the reference label maps to
# an EMPTY list (untouched re-solve); every other label MUST start `pint-`
# (asset put in on top of the reference) or `toot-` (asset taken out of it)
# and carry a NON-EMPTY list. The "asset" is component-generic and may span
# several components (a line, an HVDC link, a plant, a storage unit, or a
# composite like bus + conversion link + load).
#
# Operation schema:
#   {op: add,    component, name, params: {...}}   new component, name fresh
#   {op: zero,   component, where: {...}}          nominal capacity -> 0 and
#                                                  non-extendable (takes the
#                                                  asset out; its history
#                                                  stays inspectable)
#   {op: remove, component, where: {...}}          drop the rows entirely
#   {op: set,    component, where, attr, value}    plain attribute edit
#   {op: scale,  component, where, attr, value}    multiplicative edit
# where: {column-or-'index': value | [values]} — conjunctive selection.
# set/scale also reach the time-varying series (n.<component>_t[attr]) for
# selected rows governed by one — rows with a time-varying attr ignore the
# static column, so a static-only edit of e.g. loads p_set would be a
# silent no-op for exactly those rows.
# An operation whose selection matches nothing (or an `add` whose name
# already exists) is a HARD ERROR: a silently unchanged variant is the
# dead-key failure class the zygon harness exists to catch.

import logging

import pandas as pd
import pypsa

logger = logging.getLogger(__name__)

CLASSES = {"generators": "Generator", "links": "Link", "lines": "Line",
           "storage_units": "StorageUnit", "stores": "Store",
           "loads": "Load", "buses": "Bus", "transformers": "Transformer",
           "carriers": "Carrier"}
NOM = {"generators": "p_nom", "links": "p_nom", "lines": "s_nom",
       "storage_units": "p_nom", "stores": "e_nom", "transformers": "s_nom"}
OPS = {"add", "zero", "remove", "set", "scale"}


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
    if not mask.any():
        raise ValueError(f"{addr}: selection {where!r} matched no rows — "
                         "a no-op variant is a hard error")
    return mask


def ensure_carrier(n, params):
    carrier = (params or {}).get("carrier")
    if carrier and carrier not in n.carriers.index:
        n.add("Carrier", carrier)
        logger.info("registered missing carrier '%s'", carrier)


def apply_operation(n, spec, addr, summary):
    component = spec.get("component")
    op = spec.get("op")
    if component not in CLASSES:
        raise ValueError(f"{addr}: component must be one of "
                         f"{sorted(CLASSES)}, got {component!r}")
    if op not in OPS:
        raise ValueError(f"{addr}: op must be one of {sorted(OPS)}, "
                         f"got {op!r}")
    df = getattr(n, component)

    if op == "add":
        name = spec.get("name")
        params = dict(spec.get("params") or {})
        if not name:
            raise ValueError(f"{addr}: add needs a 'name'")
        if name in df.index:
            raise ValueError(f"{addr}: {component} '{name}' already exists "
                             "— an add that overwrites is a hard error")
        before = df.dtypes.copy()
        ensure_carrier(n, params)
        n.add(CLASSES[component], name, **params)
        df = getattr(n, component)
        # MODEL-specific static columns (e.g. eur's links.reversed bool) are
        # not pypsa attrs, so n.add leaves the new row NaN and pandas
        # coerces the whole column's dtype — model code that indexes on such
        # a column then crashes. Neutral-fill the new row and restore the
        # pre-add dtype.
        for col, dtype in before.items():
            if col in params or col not in df.columns:
                continue
            if df[col].dtype != dtype and pd.isna(df.at[name, col]):
                df.at[name, col] = False if dtype == bool else 0
                df[col] = df[col].astype(dtype)
        summary["added"].append(f"{component}:{name}")
        logger.info("%s: added %s '%s' with %s", addr, component, name,
                    params)
        return 1

    if op == "zero":
        if component not in NOM:
            raise ValueError(f"{addr}: zero not defined for {component}")
        mask = select(df, spec.get("where"), addr)
        nom = NOM[component]
        for attr in (nom, nom + "_min", nom + "_max"):
            df.loc[mask, attr] = 0.0
        df.loc[mask, nom + "_extendable"] = False
        summary["zeroed"] += list(df.index[mask])
        logger.info("%s: zeroed %s on %d %s row(s)", addr, nom,
                    int(mask.sum()), component)
        return int(mask.sum())

    if op == "remove":
        mask = select(df, spec.get("where"), addr)
        names = list(df.index[mask])
        if hasattr(n, "mremove"):
            n.mremove(CLASSES[component], names)
        else:
            n.remove(CLASSES[component], names)
        summary["removed"] += [f"{component}:{x}" for x in names]
        logger.info("%s: removed %d %s row(s)", addr, len(names), component)
        return len(names)

    attr = spec.get("attr")
    if attr not in df.columns:
        raise KeyError(f"{addr}: '{attr}' not a static attribute of "
                       f"{component}")
    mask = select(df, spec.get("where"), addr)
    value = spec.get("value")
    if op == "set":
        df.loc[mask, attr] = value
    else:  # scale
        df.loc[mask, attr] = df.loc[mask, attr].astype(float) * float(value)
    # rows whose attr is governed by a time-varying series ignore the static
    # column entirely — edit the series too, or the operation would be a
    # silent no-op for exactly those rows
    tv = getattr(n, component + "_t", None)
    tv_names = []
    if tv is not None and attr in tv:
        tv_names = [x for x in df.index[mask] if x in tv[attr].columns]
        if tv_names:
            if op == "set":
                tv[attr].loc[:, tv_names] = value
            else:  # scale
                tv[attr].loc[:, tv_names] = tv[attr][tv_names] * float(value)
    logger.info("%s: %s %s.%s on %d row(s) (%d time-varying) with value %s",
                addr, op, component, attr, int(mask.sum()), len(tv_names),
                value)
    return int(mask.sum())


def direction_of(label, reference, operations):
    if label == reference:
        if operations:
            raise ValueError(f"reference variant '{label}' must carry an "
                             "empty operation list")
        return "ref"
    for prefix in ("pint-", "toot-"):
        if label.startswith(prefix):
            if not operations:
                raise ValueError(f"variant '{label}' carries no operations "
                                 "— a no-op perturbation is a hard error")
            return prefix.rstrip("-")
    raise ValueError(f"variant '{label}' is neither the reference "
                     f"('{reference}') nor pint-*/toot-* — direction must "
                     "be mechanical")


if __name__ == "__main__":
    if snakemake.log:  # noqa: F821
        logging.basicConfig(filename=str(snakemake.log[0]),  # noqa: F821
                            level=logging.INFO)

    zcba = str(snakemake.wildcards.zcba)  # noqa: F821
    operations = list(snakemake.params.variant)  # noqa: F821
    reference = str(snakemake.params.reference)  # noqa: F821

    direction = direction_of(zcba, reference, operations)

    n = pypsa.Network(snakemake.input.network)  # noqa: F821
    summary = {"variant": zcba, "direction": direction,
               "operations": operations, "added": [], "zeroed": [],
               "removed": [], "touched": 0}
    for i, spec in enumerate(operations):
        summary["touched"] += apply_operation(
            n, dict(spec), f"variant '{zcba}' op[{i}]", summary)
    logger.info("variant '%s' (%s): %d operation(s), %d row(s) touched",
                zcba, direction, len(operations), summary["touched"])

    n.meta = dict(n.meta, single_asset_cba=summary)
    n.export_to_netcdf(snakemake.output[0])  # noqa: F821
