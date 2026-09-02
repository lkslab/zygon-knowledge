#!/usr/bin/env python3
"""Re-home the non-numeric rows parked by migrate_v2.py --split-units into
regulation.csv, where non-numeric policy belongs.

These 16 rows are real, well-sourced policy facts (a flaring commitment, a
credit-retirement volume, a land allocation for hydrogen). What they are not is
*numeric energy targets*: their `unit` carried a thing -- solar kits, hectares,
CBIOs, US dollars -- that no model consumes and no other row is comparable to.
Coercing them into the closed unit vocabulary would have made them look like
capacity or generation targets. Deleting them would lose sourced knowledge.

So they move sideways: the quantity is preserved verbatim in `scope_summary`
(prose, which is what regulation.csv is for), provenance carries over unchanged,
and `notes` records where the row came from so the move is reversible.

Idempotent: re-running skips record_ids already present in regulation.csv.

Usage: python3 tools/rehome_qualitative.py [--dry-run]
"""
import csv
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PARKED = BASE / "_work" / "qualitative_targets.csv"
DEST = BASE / "regulation.csv"

# metric -> the regulation `type` that best describes it. `mandate` rows are
# mandates; everything else here is a stated government objective, i.e. a
# target written into a plan or law.
TYPE_FOR = {"mandate": "mandate"}
DEFAULT_TYPE = "target_law"


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return list(rd), list(rd.fieldnames)


def main(dry_run=False):
    if not PARKED.exists():
        sys.exit("nothing parked; run migrate_v2.py --split-units first")
    parked, _ = read(PARKED)
    dest, cols = read(DEST)
    have = {r["record_id"] for r in dest}

    added = []
    for r in parked:
        if r["record_id"] in have:
            continue
        value, unit = r["value"].strip(), r["unit"].strip()
        summary = f"{value} {unit}".strip()
        year = r.get("year", "")
        if year and year not in unit:      # several unit strings already say "by <year>"
            summary += f" by {year}"
        added.append({
            "record_id": r["record_id"],
            "country": r["country"],
            "technology": r["technology"],
            "model_carrier": r["model_carrier"],
            "instrument_name": r["instrument_name"],
            "type": TYPE_FOR.get(r["metric"], DEFAULT_TYPE),
            # A stated plan objective is in force as policy even where the
            # underlying quantity is not legally binding; `binding` carried that
            # nuance in targets.csv and is preserved in notes below.
            "status": "in_force",
            "year": r["year"],
            "sunset_year": "",
            "scope_summary": summary,
            "source": r["source"],
            "source_url": r["source_url"],
            "retrieved": r["retrieved"],
            "confidence": r["confidence"],
            "last_updated": r["last_updated"],
            "notes": (f"Moved from targets.csv in the v1->v2 unit migration: the "
                      f"quantity ({summary}) is not expressible in the closed unit "
                      f"vocabulary. metric={r['metric']}, binding={r['binding']}. "
                      + (r["notes"] or "")).strip(),
        })

    print(f"re-homing {len(added)} row(s) into regulation.csv "
          f"({len(parked) - len(added)} already present)")
    for a in added:
        print(f"  {a['record_id']:38} {a['country']:3} {a['type']:11} {a['scope_summary'][:50]}")
    if dry_run:
        print("[dry-run] nothing written")
        return
    with open(DEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(dest + added)
    print(f"regulation.csv: {len(dest)} -> {len(dest) + len(added)} rows")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
