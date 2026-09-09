#!/usr/bin/env python3
"""Recover the sub-fuel dimension the Ember NECP import dropped.

The bulk import of Ember's NECP compilation read FUEL_CODE but not FUEL_LOWER,
which is the column that separates onshore from offshore wind, battery from
pumped hydro, hard coal from lignite. Three source rows (TOTAL / Onshore /
Offshore) all landed as `technology=wind` with byte-identical `notes`, so the
brockhaus ended up asserting that Austrian wind generation in 2030 is both
19.0 TWh and 0.0 TWh with nothing to tell the rows apart. 434 groups covering
1198 rows were in that state -- about a fifth of targets.csv.

This re-joins against the source file and restores the lost dimension:

  * `scope_note` gets the FUEL_LOWER label on every NECP row, so the rows are
    distinguishable and the contradiction dissolves into a real breakdown.
  * where FUEL_LOWER names a technology the taxonomy already has, `technology`
    and `model_carrier` are corrected too. An "offshore" row tagged `wind`
    carries an empty model_carrier and is useless to a model; tagged
    `wind_offshore` it carries `offwind` and becomes usable.

Sub-fuels with no unambiguous token (hard coal vs lignite, gas baseload vs
peaker, solid biomass vs biogas, "abated fossil") keep their aggregate token
and are separated by scope_note alone -- inventing tokens for them would be a
schema change the data does not justify.

Idempotent. Requires the Ember source; skips cleanly if it is absent.

Usage: python3 tools/backfill_necp_detail.py [--dry-run] [--source PATH]
"""
import argparse
import csv
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path.home() / "Desktop/enderpearl/data/policy/Ember_NECP_data_2024.csv"

# FUEL_LOWER -> taxonomy token, only where the mapping is unambiguous.
RETAG = {
    "Onshore": "wind_onshore",
    "Offshore": "wind_offshore",
    "Battery": "battery",
    "Nuclear": "nuclear",
    "Hydrogen": "hydrogen",
}
# Everything else keeps its aggregate token; scope_note carries the detail.
KEEP = {"TOTAL", "Other fossil", "Oil", "Solid biomass", "Biogas", "Hard coal",
        "Lignite", "Gas baseload", "Gas peaker", "Abated fossil", "Pumped hydro"}

KPI_METRIC = {"Electricity generation": "generation", "Installed capacity": "capacity"}


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return list(rd), list(rd.fieldnames)


def main(dry_run=False, src=DEFAULT_SRC):
    if not Path(src).exists():
        sys.exit(f"SKIP: Ember source not found at {src}")

    ember, _ = read(src)
    tax, _ = read(BASE / "technology_taxonomy.csv")
    carrier = {r["technology"]: r["model_carrier"] for r in tax}

    # (country, fuel_group, fuel_code, kpi, year, wem_wam) -> [FUEL_LOWER...] in
    # file order, which is the order ingest_necp.py appended them and therefore
    # the order the -2/-3 record_id suffixes follow.
    #
    # fuel_group is load-bearing in the key: BE/TOTAL/TOTAL for 2020 appears
    # four times, once under each of TOTAL, RENEWABLE, FOSSIL and OTHER, and
    # they are different facts.
    src_index = {}
    for r in ember:
        k = (r["SHORT_COUNTRY_CODE"], r["FUEL_GROUP"], r["FUEL_CODE"], r["KPI"],
             r["YEAR"], r["WEM_WAM"])
        src_index.setdefault(k, []).append((r["FUEL_LOWER"], r["VALUE"]))

    rows, cols = read(BASE / "targets.csv")
    if "scope_note" not in cols:
        sys.exit("ABORT: run migrate_v2.py --split-units first")

    named = retagged = unmatched = 0
    for r in rows:
        m = re.search(r"fuel_code=([^;]*)", r.get("notes") or "")
        if not m or "NECP" not in (r.get("notes") or ""):
            continue
        if r.get("scope_note"):
            continue    # already labelled by a previous run -- never append twice
        fuel_code = m.group(1).strip()
        kpi = re.search(r"kpi=([^;]*)", r["notes"])
        kpi = kpi.group(1).strip() if kpi else ""
        grp = re.search(r"fuel_group=([^;]*)", r["notes"])
        grp = grp.group(1).strip() if grp else ""
        # `projection` is this registry's label for the source's base-year rows,
        # which carry a blank WEM_WAM.
        scen = "" if r["scenario"] == "projection" else r["scenario"].upper()
        cands = src_index.get(
            (r["country"], grp, fuel_code, kpi, r["year"], scen), [])
        # Match on value: within a (country, fuel, kpi, year, scenario) cell the
        # sub-fuels differ by value, so the value identifies the FUEL_LOWER.
        # Where two sub-fuels share a value (TOTAL == Onshore for a landlocked
        # country) fall back to the record_id suffix, which encodes file order.
        hit = [fl for fl, v in cands if _same(v, r["value"])]
        if len(hit) > 1:
            idx = _suffix_index(r["record_id"])
            order = [fl for fl, _ in cands]
            hit = [order[idx]] if idx < len(order) else hit[:1]
        if not hit:
            unmatched += 1

        # Two coordinates are needed, not one. FUEL_LOWER separates onshore from
        # offshore wind; FUEL_CODE separates an aggregate ("all OTHER
        # generation") from a component ("OTHMISC") when both carry
        # FUEL_LOWER=TOTAL. Labelling with FUEL_LOWER alone left 186 pairs still
        # colliding. FUEL_CODE is read from `notes`, so this also labels the
        # rows that matched no source row at all.
        label = hit[0] if hit else ""
        if label and label != "TOTAL":
            r["scope_note"] = label
            if label in RETAG:
                tok = RETAG[label]
                r["technology"], r["model_carrier"] = tok, carrier[tok]
                retagged += 1
        elif fuel_code and fuel_code != "TOTAL":
            r["scope_note"] = fuel_code.lower()
        else:
            r["scope_note"] = "total"
        named += 1

    print(f"NECP rows given a sub-fuel label: {named}")
    print(f"  of which re-tagged to a precise technology token: {retagged}")
    print(f"  rows whose value matched no source row: {unmatched}")
    if dry_run:
        print("[dry-run] nothing written")
        return
    with open(BASE / "targets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _same(a, b):
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def _suffix_index(record_id):
    m = re.search(r"-(\d+)$", record_id)
    return int(m.group(1)) - 1 if m else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--source", default=str(DEFAULT_SRC))
    a = ap.parse_args()
    main(a.dry_run, a.source)
