# SPDX-License-Identifier: MIT
"""Component names that never clash with a carrier id.

PyPSA refuses an `n.add` whose name another component type already holds, and the
toy models name a Carrier after the technology (`onwind`). The generator, store or
bus for that technology therefore gets `<carrier> gen` (or another suffix), while
figures and `numbers` keep the published carrier label; `plain` maps back.
"""

from __future__ import annotations

from typing import TypeVar

import pandas as pd

GEN = " gen"
LINK = " link"
UNIT = " unit"  # Store and StorageUnit
BUS = " bus"
SUFFIXES = (GEN, LINK, UNIT, BUS)

T = TypeVar("T", pd.DataFrame, pd.Series)


def _strip(label: object) -> object:
    if isinstance(label, str):
        for suffix in SUFFIXES:
            if label.endswith(suffix):
                return label[: -len(suffix)]
    return label


def gen(carrier: str) -> str:
    """Generator name for a carrier id."""
    return f"{carrier}{GEN}"


def link(carrier: str) -> str:
    """Link name for a carrier id."""
    return f"{carrier}{LINK}"


def unit(carrier: str) -> str:
    """Store or StorageUnit name for a carrier id."""
    return f"{carrier}{UNIT}"


def bus(carrier: str) -> str:
    """Bus name for a carrier id the bus would otherwise share."""
    return f"{carrier}{BUS}"


def plain(obj: T) -> T:
    """Copy of a time-series frame (columns) or a per-component frame/series (index) with the name suffixes stripped."""
    out = obj.copy()
    if isinstance(out, pd.DataFrame) and all(isinstance(x, str) for x in out.index):
        out.index = out.index.map(lambda x: _strip(x))
    elif isinstance(out, pd.Series):
        out.index = out.index.map(lambda x: _strip(x))
    if isinstance(out, pd.DataFrame):
        out.columns = out.columns.map(lambda x: _strip(x))
    return out
