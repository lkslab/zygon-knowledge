#!/usr/bin/env python3
"""Integrate a research JSON bundle into the brockhaus tables.

Reads a JSON file with arrays keyed by table name (targets/regulation/
subsidies/assets), resolves technology aliases, fills model_carrier from the
taxonomy, and upserts by record_id (idempotent re-runs).

Provenance is enforced, not filled in. `retrieved` must come from the bundle --
the agent records when it actually read the source. An auto-stamped `retrieved`
is a fabricated provenance claim, and a hardcoded one is why every row in this
registry used to share a single date. Rows missing `source_url` or `retrieved`
are REJECTED, not warned about.

Usage:
  python3 tools/integrate_research.py bundle.json            # write
  python3 tools/integrate_research.py bundle.json --dry-run  # validate only
"""
import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TABLES = ("assets", "targets", "subsidies", "regulation")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return list(rd), list(rd.fieldnames)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bundle")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and report what would change; write nothing")
    a = ap.parse_args()

    raw = Path(a.bundle).read_text(encoding="utf-8")
    data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])  # tolerate fences/prose

    tax, _ = read_csv(BASE / "technology_taxonomy.csv")
    carrier = {r["technology"]: r["model_carrier"] for r in tax}
    valid = set(carrier)
    alias = {}
    for tr in tax:
        canon = tr["technology"].strip()
        alias[canon.lower()] = canon
        for al in str(tr["aliases"]).split(";"):
            al = al.strip().lower()
            if al:
                alias[al] = canon

    today = date.today().isoformat()
    rejected, summary = [], []

    for table, items in data.items():
        if table not in TABLES:
            continue  # ignore non-table keys like "meta"
        path = BASE / f"{table}.csv"
        existing, cols = read_csv(path)
        new_rows = []
        for it in items:
            rid = it.get("record_id", "")
            raw_tech = str(it.get("technology", "")).strip()
            tok = alias.get(raw_tech.lower(), raw_tech)

            # --- provenance gate: reject, never auto-fill ---
            if not str(it.get("source_url", "")).strip():
                rejected.append(f"{table}/{rid}: missing source_url")
                continue
            ret = str(it.get("retrieved", "")).strip()
            if not ret:
                rejected.append(f"{table}/{rid}: missing retrieved "
                                "(record when you read the source; it is not auto-filled)")
                continue
            if not DATE_RE.match(ret):
                rejected.append(f"{table}/{rid}: retrieved '{ret}' is not YYYY-MM-DD")
                continue
            if tok not in valid:
                rejected.append(f"{table}/{rid}: unknown technology '{raw_tech}'")
                continue

            row = dict(it)
            row["technology"] = tok
            row["model_carrier"] = carrier[tok]
            row["retrieved"] = ret
            row["last_updated"] = today
            new_rows.append({c: str(row.get(c, "")) for c in cols})

        ids = {r["record_id"] for r in new_rows}
        kept = [r for r in existing if r["record_id"] not in ids]
        updated = len(existing) - len(kept)
        out = kept + new_rows
        summary.append(f"{table}.csv: +{len(new_rows) - updated} new, "
                       f"{updated} updated, {len(out)} total")

        if not a.dry_run:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(out)

    for line in summary:
        print(("[dry-run] " if a.dry_run else "") + line)
    if rejected:
        print(f"\nREJECTED {len(rejected)} row(s):")
        for r in rejected:
            print("  -", r)
        sys.exit(1)


if __name__ == "__main__":
    main()
