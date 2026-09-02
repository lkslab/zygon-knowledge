# SPDX-License-Identifier: MIT
#
# Harmonised multi-network collection — zygon methods payload
# `multi-scenario`. Applies every hook function named in
# zygon_collect.quantities (defined in the agent-authored hooks module,
# zygon_collect.hooks, at the workflow root) to every network listed in
# zygon_collect.networks and writes ONE long-format CSV per quantity:
# a `network` column carrying the variant label, the hook's own index
# columns, and a `value` column.
#
# Hook contract (the agent's ONE code surface for this method):
#   def <quantity>(n) -> pandas.Series | tidy pandas.DataFrame | number
#     - Series: any (Multi)Index; collected as s.rename("value").reset_index()
#     - DataFrame: must already be tidy/long WITH a `value` column
#     - number: single-row frame (system totals)
#     - pure function of the network; no I/O, no snakemake access
#
# Any hook failure aborts the rule loudly, naming hook and network — a
# silent partial collection is the dead-key failure class this harness
# exists to catch.

import importlib.util
import json
import logging
import re
from pathlib import Path

import pandas as pd
import pypsa

logger = logging.getLogger(__name__)

QUANTITY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def load_hooks(path):
    spec = importlib.util.spec_from_file_location("zygon_hooks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tidy(result, quantity, label):
    """One hook result -> long-format frame with a leading `network` col."""
    if isinstance(result, pd.Series):
        frame = result.rename("value").reset_index()
    elif isinstance(result, pd.DataFrame):
        if "value" not in result.columns:
            raise TypeError(f"hook '{quantity}' returned a DataFrame "
                            "without a 'value' column")
        frame = result.reset_index(drop=True).copy()
    else:
        try:
            frame = pd.DataFrame({"value": [float(result)]})
        except (TypeError, ValueError):
            raise TypeError(
                f"hook '{quantity}' must return a Series, a tidy DataFrame "
                f"with a 'value' column, or a number — "
                f"got {type(result).__name__}")
    frame.insert(0, "network", label)
    return frame


if __name__ == "__main__":
    if snakemake.log:  # noqa: F821
        logging.basicConfig(filename=str(snakemake.log[0]),  # noqa: F821
                            level=logging.INFO)

    labels = [str(x) for x in snakemake.params.labels]  # noqa: F821
    networks = [str(p) for p in snakemake.input.networks]  # noqa: F821
    quantities = [str(q) for q in snakemake.params.quantities]  # noqa: F821
    csvs = [str(p) for p in snakemake.output.csvs]  # noqa: F821

    if len(labels) != len(networks):
        raise ValueError(f"zygon_collect: {len(labels)} labels for "
                         f"{len(networks)} networks — must match 1:1")
    if len(set(labels)) != len(labels):
        raise ValueError(f"zygon_collect: labels not unique: {labels}")
    bad = [q for q in quantities if not QUANTITY_RE.match(q)]
    if bad:
        raise ValueError(f"zygon_collect: invalid quantity names {bad} "
                         "(want [a-z][a-z0-9_]*)")

    hooks = load_hooks(snakemake.input.hooks)  # noqa: F821
    missing = [q for q in quantities
               if not callable(getattr(hooks, q, None))]
    if missing:
        raise ValueError(f"zygon_collect: hooks module "
                         f"{snakemake.input.hooks} defines no callable "  # noqa: F821
                         f"for: {missing}")

    frames = {q: [] for q in quantities}
    for label, path in zip(labels, networks):
        n = pypsa.Network(path)
        for q in quantities:
            try:
                result = getattr(hooks, q)(n)
            except Exception as e:
                raise RuntimeError(
                    f"hook '{q}' on network '{label}' ({path}): {e}") from e
            frames[q].append(tidy(result, q, label))
        logger.info("collected %d quantit(ies) from '%s'",
                    len(quantities), label)

    # expand() preserves quantity order, so csvs[i] belongs to quantities[i]
    for q, csv_path in zip(quantities, csvs):
        columns = {tuple(f.columns) for f in frames[q]}
        if len(columns) > 1:
            raise ValueError(f"hook '{q}' returned differing columns "
                             f"across networks: {sorted(columns)}")
        pd.concat(frames[q], ignore_index=True).to_csv(csv_path, index=False)

    manifest = {"labels": labels, "networks": networks,
                "quantities": quantities,
                "csvs": [str(Path(p)) for p in csvs]}
    Path(snakemake.output.manifest).write_text(  # noqa: F821
        json.dumps(manifest, indent=2) + "\n")
