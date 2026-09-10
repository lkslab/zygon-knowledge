#!/usr/bin/env python3
"""One-shot schema v1 -> v2 migration. Kept in-tree as the audit record.

Two independent steps, each idempotent and each refusing to half-apply:

  --drop-fuelcode   Remove `necp_fuel_code` from the four fact tables. It is a
                    pure function of `technology` (verified: 0/9299 rows
                    disagreed with the taxonomy), so carrying it on every row is
                    redundancy that can only ever drift. It stays in
                    technology_taxonomy.csv; consumers needing it join there.

  --split-units     Replace the overloaded `unit` column in targets.csv with
                    three: `unit` (closed vocabulary, pure physical dimension),
                    `basis` (closed vocabulary, the denominator/reference that
                    makes two percentages comparable), and `scope_note` (free
                    text, deliberately non-load-bearing -- never in a grouping
                    key, never parsed).

                    Why this matters: registry.py:select_targets() groups by
                    (country, technology, metric, unit). With 155 distinct unit
                    strings -- 114 rows carrying free text like "GW WtE
                    incineration (qualitative steady-development goal)" -- most
                    groups were singletons, so scenario-preference and
                    year-bracketing silently did nothing. Closing the vocabulary
                    is what switches those back on.

                    The mapping is an explicit literal table, not a regex. A
                    regex over "% ethanol in gasoline (max ceiling)" is exactly
                    how you silently mangle a handful of rows. Any unit string
                    not in the table aborts the run.

Usage:
  python3 tools/migrate_v2.py --drop-fuelcode
  python3 tools/migrate_v2.py --split-units [--dry-run]
"""
import argparse
import csv
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TABLES = ("assets", "targets", "subsidies", "regulation")

def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return list(rd), list(rd.fieldnames)


def write(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def drop_fuelcode():
    tax, _ = read(BASE / "technology_taxonomy.csv")
    expect = {r["technology"]: r["necp_fuel_code"] for r in tax}
    total = drift = 0
    for t in TABLES:
        path = BASE / f"{t}.csv"
        rows, cols = read(path)
        if "necp_fuel_code" not in cols:
            print(f"{t}.csv: already dropped")
            continue
        for r in rows:                       # refuse to drop information
            total += 1
            if r["necp_fuel_code"] != expect.get(r["technology"], ""):
                drift += 1
        write(path, rows, [c for c in cols if c != "necp_fuel_code"])
        print(f"{t}.csv: necp_fuel_code dropped ({len(rows)} rows)")
    if drift:
        sys.exit(f"ABORT: {drift}/{total} rows disagreed with the taxonomy -- "
                 "the column was NOT redundant. Restore and investigate.")
    print(f"verified redundant on {total} rows before dropping")


def split_units(dry_run=False):
    from unit_map import UNIT_MAP, QUALITATIVE, UNITS, BASIS
    path = BASE / "targets.csv"
    rows, cols = read(path)
    if "basis" in cols:
        print("targets.csv: already split")
        return

    known = set(UNIT_MAP) | QUALITATIVE
    unmapped = sorted({r["unit"] for r in rows if r["unit"] not in known})
    if unmapped:
        print(f"ABORT: {len(unmapped)} unit string(s) absent from the map:")
        for u in unmapped:
            print(f"  {u!r}")
        sys.exit(1)

    moved, kept = [], []
    for r in rows:
        if r["unit"] in QUALITATIVE:
            moved.append(r)
            continue
        u, b, note = UNIT_MAP[r["unit"]]
        assert u in UNITS, f"bad unit token {u!r}"
        assert b in BASIS, f"bad basis token {b!r}"
        r["unit"], r["basis"] = u, b
        r["scope_note"] = note
        kept.append(r)

    out_cols = []
    for c in cols:                            # keep basis/scope_note beside unit
        out_cols.append(c)
        if c == "unit":
            out_cols += ["basis", "scope_note"]

    print(f"targets.csv: {len(rows)} rows -> {len(kept)} kept, "
          f"{len(moved)} non-numeric moved out")
    print(f"  distinct unit strings: {len({r for r in UNIT_MAP})} -> {len(UNITS)} (closed)")
    if dry_run:
        print("[dry-run] nothing written")
        return
    write(path, kept, out_cols)
    if moved:
        write(BASE / "_work" / "qualitative_targets.csv", moved, cols)
        print(f"  non-numeric rows parked in _work/qualitative_targets.csv "
              f"for re-homing into regulation.csv")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop-fuelcode", action="store_true")
    ap.add_argument("--split-units", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.drop_fuelcode:
        drop_fuelcode()
    if a.split_units:
        split_units(a.dry_run)
    if not (a.drop_fuelcode or a.split_units):
        ap.error("pick a step")
