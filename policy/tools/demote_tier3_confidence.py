#!/usr/bin/env python3
"""Demote `confidence: high` rows whose only citation is a tier-3 source.

MAINTAINER.md's own provenance rule says a tier-3 source -- press, trade blog,
wiki, consultancy -- cannot back a high-confidence claim. 1809 rows violated it.
Widening the source tiering to recognise government domains worldwide (any
.gov/.gouv/.gob/.go/.govt, not just an EU allowlist) reclassified 533 of those
as the tier-1 ministry citations they always were. This handles the genuine
remainder: 1276 rows citing en.wikipedia.org (290), pv-magazine.com (52),
power-technology.com (34) and ~490 other outlets.

`high` -> `med`, not `high` -> `low`. A strict reading of the rule says tier 3
should only ever be `low`, but 3187 of 9299 rows cite tier-3 sources, and
demoting them all to `low` would paint a third of the registry as untrustworthy
when most are competent trade reporting of a real project. `med` is the honest
middle. The rule in MAINTAINER.md is amended to match: tier 3 -> at most `med`,
and check_registry.py enforces only the `high` prohibition.

Every touched row records the demotion in `notes`, so it is visible and
reversible -- re-cite the row to a primary source and confidence can go back up.

Idempotent. Usage: python3 tools/demote_tier3_confidence.py [--dry-run]
"""
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TABLES = ("assets", "targets", "subsidies", "regulation")
MARK = "confidence auto-demoted from high"


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return list(rd), list(rd.fieldnames)


def main(dry_run=False):
    sources, _ = read(BASE / "sources.csv")
    tier = {r["url"]: r["tier"] for r in sources}
    today = date.today().isoformat()
    total = Counter()
    pub = Counter()

    for t in TABLES:
        path = BASE / f"{t}.csv"
        rows, cols = read(path)
        n = 0
        for r in rows:
            if r.get("confidence") != "high":
                continue
            if tier.get(r.get("source_url")) != "3":
                continue
            r["confidence"] = "med"
            note = (r.get("notes") or "").strip()
            r["notes"] = (f"{note} [{MARK}: tier-3 source, {today}]").strip()
            r["last_updated"] = today
            pub[r["source_url"].split("/")[2] if "//" in r["source_url"] else "?"] += 1
            n += 1
        total[t] = n
        if n and not dry_run:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)

    print(f"{'[dry-run] ' if dry_run else ''}demoted high -> med: "
          f"{sum(total.values())} row(s) {dict(total)}")
    if pub:
        print("  top publishers:",
              ", ".join(f"{k} x{v}" for k, v in pub.most_common(5)))


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
