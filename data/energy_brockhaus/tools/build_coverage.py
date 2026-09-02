#!/usr/bin/env python3
"""Regenerate coverage.csv from the data.

coverage.csv answers the question the brockhaus exists to answer honestly: is a
gap a gap in the *world* ("this country has no 2050 target") or a gap in *us*
("nobody has collected it yet")? Getting that wrong makes an agent either
fabricate or apologise for nothing.

The file it replaces was hand-maintained and had 15 rows for 143 countries, so
coverage_status() fell through to "missing" for roughly 138 of them -- reporting
absence of information as absence of a target. Here every (country, table) cell
in the country universe gets a row, including the empty ones, so "missing" is a
statement rather than a default.

The verdict rule lives in _qa/check_registry.py:derive_coverage and is imported
here rather than duplicated, so the generated file and the check that guards it
cannot drift apart. Coverage also *decays*: a cell whose newest `retrieved` is
older than two years is demoted a rung and says so.

Usage: python3 tools/build_coverage.py [--dry-run]
"""
import csv
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "_qa"))
sys.path.insert(0, str(BASE / "tools"))

from check_registry import (derive_coverage, load, TABLES, FLOOR,   # noqa: E402
                            CELL_ROLLUP)
from countries import WORLD                                        # noqa: E402

COLS = ["country", "record_type", "technology_group", "year_min", "year_max",
        "source_count", "row_count", "best_tier", "last_reviewed",
        "completeness", "known_gaps"]


def to_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def main(dry_run=False):
    tables = {t: load(t) for t in TABLES}
    sources = load("sources")
    tax = load("technology_taxonomy")
    group_of = {r["technology"]: r["group"] for r in tax}
    today = date.today()

    derived = derive_coverage(tables, sources, today)

    # index rows per (country, table) and per (country, table, tech group)
    cells, by_group = {}, {}
    for t, rows in tables.items():
        for r in rows:
            c = r.get("country")
            cells.setdefault((c, t), []).append(r)
            g = group_of.get(r.get("technology"), "")
            if g:
                by_group.setdefault((c, t, g), []).append(r)

    out = []

    def emit(country, table, group, rows, verdict, gaps):
        years = {to_int(r.get("year")) for r in rows} - {None}
        out.append({
            "country": country, "record_type": table, "technology_group": group,
            "year_min": min(years) if years else "",
            "year_max": max(years) if years else "",
            "source_count": len({r.get("source_url") for r in rows if r.get("source_url")}),
            "row_count": len(rows),
            "best_tier": min((sources_tier.get(r.get("source_url"), "3")
                              for r in rows), default=""),
            "last_reviewed": today.isoformat(),
            "completeness": verdict, "known_gaps": gaps,
        })

    sources_tier = {r["url"]: r["tier"] for r in sources}

    for country in sorted(WORLD):
        for t in TABLES:
            rows = cells.get((country, t), [])
            verdict, _, _, gaps = derived.get(
                (country, t), ("missing", 0, "", ""))
            if not rows and not gaps:
                gaps = "not collected"
            elif rows and not gaps and len(rows) < FLOOR[t]:
                gaps = f"below floor ({len(rows)}/{FLOOR[t]} rows)"
            # "*" not "aggregate": the taxonomy has a technology *group* called
            # `aggregate` (renewables, ALL, other), and reusing the word made
            # the group row silently shadow the cell roll-up on read-back.
            emit(country, t, CELL_ROLLUP, rows, verdict, gaps)

            groups = sorted({g for (c, tt, g) in by_group if c == country and tt == t})
            for g in groups:
                grows = by_group[(country, t, g)]
                # A technology group inherits the cell's verdict unless it is
                # itself thin -- a country can have eight solid solar rows and
                # nothing at all on storage.
                gv = verdict if len(grows) >= FLOOR[t] else "seed"
                emit(country, t, g, grows, gv, "")

    print(f"coverage.csv: {len(out)} rows "
          f"({len(WORLD)} countries x {len(TABLES)} tables + technology groups)")
    verdicts = {}
    for r in out:
        if r["technology_group"] == CELL_ROLLUP:
            verdicts[r["completeness"]] = verdicts.get(r["completeness"], 0) + 1
    print("  aggregate cells by verdict:", dict(sorted(verdicts.items())))
    stale = sum(1 for r in out if r["known_gaps"].startswith("stale"))
    print(f"  cells demoted for staleness: {stale}")

    if dry_run:
        print("[dry-run] nothing written")
        return
    with open(BASE / "coverage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
