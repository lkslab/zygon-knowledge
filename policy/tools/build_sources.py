#!/usr/bin/env python3
"""Regenerate sources.csv from the inline source_urls in the data tables.

The provenance index: one row per distinct source document, auto-tiered by
domain. Tier drives two things downstream -- the coverage verdict
(build_coverage.py) and the confidence ceiling (_qa/check_registry.py forbids a
tier-3 source backing a `confidence: high` row).

Idempotent and non-destructive: rows already in sources.csv (matched by url) are
preserved verbatim (keeps curated titles/dates); only missing documents are
added. Many rows sharing one url (e.g. the whole Ember NECP import) collapse to
one row.

Stdlib only. Run after any import.
"""
import csv
import hashlib
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parents[1]
TABLES = ["assets", "targets", "subsidies", "regulation"]
SRC = BASE / "sources.csv"
COLS = ["source_id", "title", "publisher", "url", "tier", "published", "retrieved", "notes"]

# Tier 1 = primary government / legislator / official gazette, worldwide.
# Tier 2 = primary data providers, multilateral bodies, official company sites.
# Everything else (press, trade, wiki, think-tank) = tier 3.
#
# The pattern below matches any government domain in any country, so a ministry
# resolves to tier 1 without needing an entry per state. The EU-only allowlist
# this replaced made every non-European ministry a tier-3 "press" source, which
# accounted for 533 of the 1809 rows that carried `confidence: high` on an
# apparently tier-3 citation. Covers .gov / .gov.xx plus the non-English
# equivalents (.gouv, .gob, .go, .govt, .gv).
GOV_RE = re.compile(
    r"(^|\.)(gov|gouv|gob|govt|gv|go)(\.[a-z]{2,3})?$"      # ends: bmwk.gov.sg, x.gouv.fr
    r"|(^|\.)(gov|gouv|gob|govt|gv|go)\.[a-z]{2,3}$"        # ema.gov.sg
)
TIER1_SUFFIX = (".gc.ca", ".admin.ch", ".europa.eu", ".parliament.uk")
TIER1 = ("eur-lex.europa.eu", "ec.europa.eu", "gesetze-im-internet.de",
         "regjeringen.no", "ens.dk", "miteco.gob.es", "bmwk.de",
         "bundeswirtschaftsministerium.de", "bundesnetzagentur.de", "admie.gr",
         "herema.gr", "legifrance.gouv.fr", "normattiva.it",
         "unfccc.int", "sedeaplicaciones.minetur.gob.es")
# Authoritative compilers and primary data providers. Not government, but not
# press either: a curated legal/statistical database is a legitimate citation
# for a `med` claim, and for `high` when it reproduces a primary instrument.
TIER2 = ("ember-energy.org", "ember-climate.org", "iea.org", "irena.org",
         "globalenergymonitor.org", "gem.wiki", "worldbank.org", "iaea.org",
         "irena.int", "un.org", "undp.org", "adb.org", "afdb.org", "ebrd.com",
         "eib.org", "entsoe.eu", "climateactiontracker.org", "enerdata.net",
         "climate-laws.org", "climatepolicydatabase.org", "lse.ac.uk",
         "world-nuclear.org", "irenastat.irena.org", "energypolicy.columbia.edu",
         # UN bodies and their legal/statistical databases. FAOLEX reproduces
         # national gazette texts, so it is a compiler of primary instruments in
         # the same sense as climate-laws.org -- not press.
         "fao.org", "faolex.fao.org", "unep.org", "unido.org", "uneca.org",
         "esmap.org", "seforall.org", "ren21.net", "globalccsinstitute.com",
         "shell.com", "equinor.com", "rwe.com", "airliquide.com", "norlights.com",
         "porthosco2.nl", "aramis-ccs.com", "eni.com",
         "northernendurancepartnership.co.uk", "eastcoastcluster.co.uk",
         "heidelbergmaterials.com", "stegra.com", "yara.com", "iberdrola.com",
         "lhyfe.com", "drax.com", "metlen.com", "eavor.com", "greenh2atlantic.com",
         "hoestptxesbjerg.dk", "great-sea-interconnector.com",
         "gregy-interconnector.gr", "windfloat-atlantic.com", "oceanwinds.com",
         "edf.fr", "geothermie.nl", "erdwerk.com", "refhyne.eu", "engie.com")


def tier_for(netloc):
    d = netloc.lower()
    if GOV_RE.search(d):
        return "1"
    if any(d == s.lstrip(".") or d.endswith(s) for s in TIER1_SUFFIX):
        return "1"
    if any(m in d for m in TIER1):
        return "1"
    if any(m in d for m in TIER2):
        return "2"
    return "3"


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def main():
    existing = read_csv(SRC)
    have = {r["url"]: r for r in existing}

    # collect distinct urls + a representative `source` label + citation count
    label, count = {}, {}
    for t in TABLES:
        for r in read_csv(BASE / f"{t}.csv"):
            u = (r.get("source_url") or "").strip()
            if not u:
                continue
            count[u] = count.get(u, 0) + 1
            label.setdefault(u, (r.get("source") or "").strip())

    today = date.today().isoformat()
    rows, added = [], 0
    for u in sorted(label):
        if u in have:
            rows.append(have[u])
            continue
        netloc = urlparse(u).netloc.replace("www.", "")
        first = netloc.split(".")[0] if netloc else "src"
        sid = f"{first}-{hashlib.md5(u.encode()).hexdigest()[:6]}"
        rows.append({
            "source_id": sid, "title": label[u] or netloc, "publisher": netloc,
            "url": u, "tier": tier_for(netloc), "published": "",
            "retrieved": today, "notes": f"auto-indexed; cited by {count[u]} row(s)",
        })
        added += 1

    rows.sort(key=lambda r: (r.get("tier", ""), r.get("publisher", "")))
    with open(SRC, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    by_tier = {}
    for r in rows:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + 1
    print(f"sources.csv: {len(rows)} documents ({added} newly added, "
          f"{len(rows) - added} preserved)")
    print("by tier:", dict(sorted(by_tier.items())))


def retier():
    """Re-apply tier_for() to every row, overwriting stored tiers.

    build_sources() preserves existing rows verbatim, which is right for curated
    titles but wrong after the tier rules themselves change -- so widening the
    domain lists needs this explicit, separate pass."""
    rows = read_csv(SRC)
    changed = 0
    for r in rows:
        new = tier_for(urlparse(r["url"]).netloc.replace("www.", ""))
        if new != r.get("tier"):
            r["tier"], changed = new, changed + 1
    with open(SRC, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"retier: {changed} of {len(rows)} source tiers changed")


if __name__ == "__main__":
    import sys
    retier() if "--retier" in sys.argv else main()
