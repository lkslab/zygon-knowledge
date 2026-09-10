#!/usr/bin/env python3
"""Move self-contradicting rows out of targets.csv into quarantine.

A contradiction here means: two or more rows record *literally identical*
coordinates -- country, technology, metric, unit, basis, year, scenario,
scope_note and the full `notes` provenance string -- and assert different
values. Nothing in the table can tell a consumer which one to believe.

All of them come from one bulk import. Ember's NECP compilation distinguishes
sub-fuels in a FUEL_LOWER column that the importer never read, so e.g. Estonia's
2030 wind capacity landed twice, 2.85 GW (onshore) and 0.0 GW (offshore), with
byte-identical provenance. backfill_necp_detail.py recovers that column for the
rows it can match against the source; this handles the residue it could not.

Quarantine rather than pick a winner: choosing the larger value would silently
invent a total, and choosing the first would encode file order as truth. The
rows keep their provenance in _work/contradictory_targets.csv and are fully
recoverable by re-importing Ember with FUEL_LOWER carried through.

Idempotent. Usage: python3 tools/quarantine_contradictions.py [--dry-run]
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TARGETS = BASE / "targets.csv"
QUARANTINE = BASE / "_work" / "contradictory_targets.csv"

# Every coordinate the row records about *what* it measures. Deliberately
# includes `notes`: if two rows differ there, they are different facts that the
# schema under-distinguishes (a WARN), not a contradiction (a FAIL).
KEY = ["country", "technology", "metric", "unit", "basis", "year", "scenario",
       "scope_note", "notes"]


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return list(rd), list(rd.fieldnames)


def main(dry_run=False):
    rows, cols = read(TARGETS)
    groups = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k, "") for k in KEY)].append(r)

    bad_ids, groups_hit = set(), 0
    for g in groups.values():
        if len(g) > 1 and len({r["value"] for r in g}) > 1:
            groups_hit += 1
            bad_ids.update(r["record_id"] for r in g)

    if not bad_ids:
        print("no contradictions; nothing to quarantine")
        return

    keep = [r for r in rows if r["record_id"] not in bad_ids]
    move = [r for r in rows if r["record_id"] in bad_ids]
    print(f"quarantining {len(move)} row(s) across {groups_hit} contradicting group(s)")
    for r in move[:6]:
        print(f"  {r['record_id']:46} {r['country']}/{r['technology']}/"
              f"{r['metric']} {r['year']} = {r['value']}")
    if len(move) > 6:
        print(f"  ...and {len(move) - 6} more")
    print(f"targets.csv: {len(rows)} -> {len(keep)} rows")

    if dry_run:
        print("[dry-run] nothing written")
        return

    QUARANTINE.parent.mkdir(exist_ok=True)
    prior = []
    if QUARANTINE.exists():
        prior, _ = read(QUARANTINE)
    have = {r["record_id"] for r in prior}
    with open(QUARANTINE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(prior + [r for r in move if r["record_id"] not in have])
    with open(TARGETS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(keep)


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
