#!/usr/bin/env python3
"""check_registry — is the energy brockhaus internally consistent and honestly
provenanced?

A dumb, mechanical oracle in the referee's style: no AI, no judgment about
whether a target is *right*, only whether the tables say what they claim to say.
Exit 1 iff any FAIL.

  closed-vocab-unit     units and bases are in the closed vocabulary. Free-text
                        units are what broke select_targets(): its grouping key
                        includes `unit`, so a unique string made a row its own
                        group and scenario-preference silently did nothing.
  singleton-group       WARN when a group is alone but another group differs
                        only by `basis` — the regression guard for the split.
  taxonomy-orphan       technology exists; model_carrier matches the taxonomy.
  source-url-shape      URL parses and is registered in sources.csv. OFFLINE by
                        construction: liveness checking would violate the
                        no-downloads rule and make the oracle non-deterministic.
  tier-confidence       a tier-3 source (press, wiki, trade blog) may not back a
                        `confidence: high` row. MAINTAINER.md's own rule.
  duplicate-fact        same (country, technology, metric, unit, basis, year,
                        scenario) but a different value — a contradiction, not a
                        duplicate. The old validate() missed these entirely.
  cross-table           retire before build, end before start, orphan instruments.
  bloc-membership       every `country` is an ISO-2 code, a bloc, or the wildcard.
  coverage-freshness    re-derives coverage and diffs it against coverage.csv,
                        so a hand-edited or stale file cannot pass unnoticed.
  year-range            years inside [1900, 2100].

Usage: python3 _qa/check_registry.py [--json]
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parent.parent

sys.path.insert(0, str(REPO / "referee"))
sys.path.insert(0, str(BASE / "tools"))
from common import Report                                    # noqa: E402
from countries import WORLD_SET, WILDCARD                     # noqa: E402
from unit_map import UNITS, BASIS                             # noqa: E402

TABLES = ["assets", "targets", "subsidies", "regulation"]
# How many rows a (country, table) cell needs before it stops being a `seed`.
FLOOR = {"targets": 8, "assets": 8, "subsidies": 3, "regulation": 4}
# technology_group value for a cell-level roll-up row. Not "aggregate":
# that is a real technology group in the taxonomy and the two would collide.
CELL_ROLLUP = "*"
STALE_MONTHS = 24


def load(name):
    path = BASE / f"{name}.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def to_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def months_between(iso, today):
    try:
        y, m, _ = (int(p) for p in iso.split("-"))
    except (ValueError, AttributeError):
        return None
    return (today.year - y) * 12 + (today.month - m)


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def check_units(rep, targets):
    bad_u = Counter(r["unit"] for r in targets if r.get("unit") not in UNITS)
    bad_b = Counter(r.get("basis", "") for r in targets
                    if r.get("basis", "") not in BASIS)
    if bad_u:
        for u, n in bad_u.most_common(10):
            rep.fail("closed-vocab-unit", f"{n} row(s) carry unit {u!r}, "
                                          "which is not in the closed vocabulary")
    if bad_b:
        for b, n in bad_b.most_common(10):
            rep.fail("closed-vocab-unit", f"{n} row(s) carry basis {b!r}, "
                                          "which is not in the closed vocabulary")
    if not bad_u and not bad_b:
        rep.ok("closed-vocab-unit",
               f"{len(targets)} target rows: all units in {len(UNITS)}-token "
               f"vocabulary, all bases in {len(BASIS)}-token vocabulary")


def check_singletons(rep, targets):
    keys = ["country", "technology", "metric", "unit", "basis"]
    groups = defaultdict(list)
    for r in targets:
        groups[tuple(r.get(k, "") for k in keys)].append(r)
    singles = {k for k, v in groups.items() if len(v) == 1}
    # A singleton is suspicious only when dropping `basis` would have merged it
    # into a larger group -- that is the shape a re-introduced free-text unit
    # would take.
    by_nobasis = defaultdict(set)
    for k in groups:
        by_nobasis[k[:4]].add(k[4])
    suspect = [k for k in singles if len(by_nobasis[k[:4]]) > 1]
    if suspect:
        rep.warn("singleton-group",
                 f"{len(suspect)} group(s) are alone yet share "
                 "(country, technology, metric, unit) with another basis — "
                 f"e.g. {suspect[0][:3]} basis={suspect[0][4]!r}; check the "
                 "bases are genuinely different denominators")
    else:
        rep.ok("singleton-group",
               f"{len(groups)} groups, {len(singles)} singleton — none caused "
               "by a basis that should have merged")


def check_taxonomy(rep, tables, tax):
    valid = {r["technology"].lower() for r in tax}
    carrier = {r["technology"].lower(): r["model_carrier"] for r in tax}
    bad = []
    for t, rows in tables.items():
        for r in rows:
            tk = (r.get("technology") or "").lower()
            if tk and tk not in valid:
                bad.append(f"{t}/{r['record_id']}: technology {r['technology']!r} "
                           "not in taxonomy")
            elif tk and r.get("model_carrier", "") != carrier.get(tk, ""):
                bad.append(f"{t}/{r['record_id']}: model_carrier "
                           f"{r.get('model_carrier')!r} != taxonomy "
                           f"{carrier.get(tk)!r}")
    for b in bad[:10]:
        rep.fail("taxonomy-orphan", b)
    if len(bad) > 10:
        rep.fail("taxonomy-orphan", f"...and {len(bad) - 10} more")
    if not bad:
        rep.ok("taxonomy-orphan", f"all technologies resolve against "
                                  f"{len(valid)} taxonomy tokens")


def check_sources(rep, tables, sources):
    known = {r["url"] for r in sources}
    unregistered, malformed = [], []
    for t, rows in tables.items():
        for r in rows:
            u = (r.get("source_url") or "").strip()
            p = urlparse(u)
            if not u or p.scheme not in ("http", "https") or not p.netloc:
                malformed.append(f"{t}/{r['record_id']}: source_url {u!r}")
            elif u not in known:
                unregistered.append(f"{t}/{r['record_id']}: {u} not in sources.csv")
    for m in malformed[:5]:
        rep.fail("source-url-shape", m)
    for m in unregistered[:5]:
        rep.fail("source-url-shape", m)
    extra = len(malformed) + len(unregistered) - min(5, len(malformed)) - min(5, len(unregistered))
    if extra > 0:
        rep.fail("source-url-shape", f"...and {extra} more")
    if not malformed and not unregistered:
        rep.ok("source-url-shape", f"every row cites one of {len(known)} "
                                   "registered sources (shape checked offline)")


def check_tier_confidence(rep, tables, sources):
    tier = {r["url"]: r["tier"] for r in sources}
    bad = defaultdict(int)
    pub = Counter()
    for t, rows in tables.items():
        for r in rows:
            if r.get("confidence") == "high" and tier.get(r.get("source_url")) == "3":
                bad[t] += 1
                pub[urlparse(r["source_url"]).netloc.replace("www.", "")] += 1
    total = sum(bad.values())
    if total:
        rep.fail("tier-confidence",
                 f"{total} row(s) carry confidence=high on a tier-3 source "
                 f"({dict(bad)}); worst offenders: "
                 + ", ".join(f"{k} x{v}" for k, v in pub.most_common(3)))
    else:
        rep.ok("tier-confidence",
               "no row claims confidence=high on a tier-3 (press/wiki) source")


def check_duplicate_facts(rep, targets):
    """Two grades of collision, and they are not the same problem.

    FAIL -- rows whose every recorded coordinate is identical, `notes` included,
    yet whose values differ. Nothing in the table can adjudicate them; they are
    corrupt and belong in quarantine.

    WARN -- rows that agree on the queryable key but differ in `notes`. They are
    distinct facts the schema under-distinguishes (typically an aggregate and
    its components from one bulk import). Real imprecision, worth seeing, but a
    consumer reading `notes` can still tell them apart."""
    queryable = ["country", "technology", "metric", "unit", "basis", "year",
                 "scenario", "scope_note"]
    full = queryable + ["notes"]

    def collisions(keys):
        seen = defaultdict(list)
        for r in targets:
            seen[tuple(r.get(k, "") for k in keys)].append(r)
        return [(k, v) for k, v in seen.items()
                if len({x.get("value") for x in v}) > 1]

    hard = collisions(full)
    soft = collisions(queryable)

    for k, v in hard[:6]:
        rep.fail("duplicate-fact",
                 f"{k[0]}/{k[1]}/{k[2]} {k[5]} ({k[6]}): identical provenance, "
                 "conflicting values "
                 + ", ".join(f"{x['value']} [{x['record_id']}]" for x in v))
    if len(hard) > 6:
        rep.fail("duplicate-fact", f"...and {len(hard) - 6} more — run "
                                   "tools/quarantine_contradictions.py")
    if not hard:
        rep.ok("duplicate-fact",
               "no two rows assert different values under identical provenance")

    under = len(soft) - len(hard)
    if under > 0:
        rep.warn("duplicate-fact",
                 f"{under} group(s) share the queryable key but differ in notes "
                 "— an aggregate and its components that the schema cannot "
                 "separate; consumers must read notes to disambiguate")


def check_cross_table(rep, tables):
    issues = []
    for r in tables["assets"]:
        y, ry = to_int(r.get("year")), to_int(r.get("retire_year"))
        if y and ry and ry < y:
            issues.append(f"assets/{r['record_id']}: retires {ry} before built {y}")
    for r in tables["subsidies"]:
        s, e = to_int(r.get("year_start")), to_int(r.get("year_end"))
        if s and e and e < s:
            issues.append(f"subsidies/{r['record_id']}: ends {e} before starts {s}")
    for r in tables["regulation"]:
        y, sy = to_int(r.get("year")), to_int(r.get("sunset_year"))
        if y and sy and sy < y:
            issues.append(f"regulation/{r['record_id']}: sunsets {sy} before {y}")
    for i in issues[:8]:
        rep.warn("cross-table", i)
    if len(issues) > 8:
        rep.warn("cross-table", f"...and {len(issues) - 8} more")
    if not issues:
        rep.ok("cross-table", "no asset retires before it is built, no "
                              "instrument ends before it starts")


def check_blocs(rep, tables, blocs):
    known = WORLD_SET | {r["bloc"] for r in blocs} | {"EU", "EU27", WILDCARD}
    bad = Counter(r["country"] for t in tables.values() for r in t
                  if r.get("country") not in known)
    if bad:
        rep.fail("bloc-membership",
                 f"{sum(bad.values())} row(s) use a country code that is neither "
                 f"ISO-2 nor a bloc: {dict(bad.most_common(8))}")
    else:
        rep.ok("bloc-membership",
               f"every country code is ISO-2, one of {len({r['bloc'] for r in blocs})} "
               "blocs, or the wildcard")


def derive_coverage(tables, sources, today):
    """The single definition of a coverage verdict; build_coverage.py imports
    this so the generated file and the check can never drift apart."""
    tier = {r["url"]: r["tier"] for r in sources}
    cells = defaultdict(list)
    for t, rows in tables.items():
        for r in rows:
            if r.get("country") in WORLD_SET:
                cells[(r["country"], t)].append(r)

    out = {}
    for (country, t), rows in cells.items():
        n = len(rows)
        tiers = [tier.get(r.get("source_url"), "3") for r in rows]
        best = min(tiers) if tiers else "3"
        any_high = any(r.get("confidence") == "high" for r in rows)
        years = {to_int(r.get("year")) for r in rows} - {None}
        banded = (any(2028 <= y <= 2032 for y in years)
                  and any(2040 <= y <= 2050 for y in years))

        if n == 0:
            verdict = "missing"
        elif n < FLOOR[t]:
            verdict = "seed"
        elif best <= "2" and any_high and (t != "targets" or banded):
            verdict = "complete"
        else:
            verdict = "partial"

        gaps = ""
        ages = [months_between(r.get("retrieved", ""), today) for r in rows]
        ages = [a for a in ages if a is not None]
        if ages and min(ages) > STALE_MONTHS:
            verdict = {"complete": "partial", "partial": "seed"}.get(verdict, verdict)
            newest = max(r.get("retrieved", "") for r in rows)
            gaps = f"stale: newest retrieved {newest[:7]}"
        out[(country, t)] = (verdict, n, best, gaps)
    return out


def check_coverage_freshness(rep, tables, sources, coverage, today):
    derived = derive_coverage(tables, sources, today)
    stored = {(r["country"], r["record_type"]): r["completeness"]
              for r in coverage if r.get("technology_group") == CELL_ROLLUP}
    if not stored:
        rep.fail("coverage-freshness",
                 "coverage.csv has no cell roll-up rows — run tools/build_coverage.py")
        return
    mismatch = [(k, v[0], stored.get(k)) for k, v in derived.items()
                if stored.get(k) != v[0]]
    missing_cells = len(WORLD_SET) * len(TABLES) - len(stored)
    if mismatch:
        for k, want, got in mismatch[:6]:
            rep.fail("coverage-freshness",
                     f"{k[0]}/{k[1]}: coverage.csv says {got!r}, data says {want!r}")
        if len(mismatch) > 6:
            rep.fail("coverage-freshness", f"...and {len(mismatch) - 6} more "
                                           "— run tools/build_coverage.py")
    elif missing_cells > 0:
        rep.fail("coverage-freshness",
                 f"{missing_cells} (country, table) cell(s) absent from "
                 "coverage.csv — run tools/build_coverage.py")
    else:
        rep.ok("coverage-freshness",
               f"coverage.csv matches the data on all {len(stored)} cells")


def check_years(rep, tables):
    bad = []
    for t, rows in tables.items():
        for r in rows:
            for col in ("year", "retire_year", "baseline_year", "sunset_year",
                        "year_start", "year_end"):
                y = to_int(r.get(col))
                if y is not None and not (1900 <= y <= 2100):
                    bad.append(f"{t}/{r['record_id']}: {col}={y}")
    for b in bad[:8]:
        rep.fail("year-range", b)
    if not bad:
        rep.ok("year-range", "all years within [1900, 2100]")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", dest="as_json", action="store_true")
    args = ap.parse_args()

    rep = Report("check_registry")
    tables = {t: load(t) for t in TABLES}
    sources = load("sources")
    tax = load("technology_taxonomy")
    blocs = load("blocs")
    coverage = load("coverage")
    today = date.today()

    check_units(rep, tables["targets"])
    check_singletons(rep, tables["targets"])
    check_taxonomy(rep, tables, tax)
    check_sources(rep, tables, sources)
    check_tier_confidence(rep, tables, sources)
    check_duplicate_facts(rep, tables["targets"])
    check_cross_table(rep, tables)
    check_blocs(rep, tables, blocs)
    check_coverage_freshness(rep, tables, sources, coverage, today)
    check_years(rep, tables)

    return rep.emit(args.as_json)


if __name__ == "__main__":
    sys.exit(main())
