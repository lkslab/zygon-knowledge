#!/usr/bin/env python3
"""Generate blocs.csv -- which supranational bodies a country belongs to.

This replaces the hardcoded `EU_CODES = {"EU", "EU27"}` in registry.py, which
had a real correctness bug behind it: country_filter() unioned EU-level rows
into *every* country's query, not just member states. A pack for Nigeria came
back carrying the EU Renewable Energy Directive. Membership has to be a lookup.

Long format, one row per (bloc, member), so a country can belong to several --
NG is in AU, ECOWAS and (via the wildcard) UNFCCC at the same time.

`kind` decides whether a bloc's rows are unioned into a member's query:
  supranational_binding  law that binds members directly (EU)          -> union
  intergovernmental      shared targets, nationally implemented        -> union
  global_instrument      treaty every party is bound by (Paris/NDC)    -> union
  global_sectoral        one sector only (IMO shipping, ICAO aviation) -> opt-in
Sectoral bodies are excluded by default because an international shipping
target is not a national energy target, and unioning it into all 190 countries
is noise, not coverage.

member = "*" means every country in the universe.

Usage: python3 tools/build_blocs.py
"""
import csv
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "blocs.csv"
COLS = ["bloc", "member", "bloc_name", "kind", "notes"]

EU27 = ("AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO "
        "SK SI ES SE").split()

# African Union: all 55 member states, ISO-2. (SADR/Western Sahara has no
# ISO-3166-1 alpha-2 code in our universe and is omitted.)
AU = ("DZ AO BJ BW BF BI CM CV CF TD KM CD CG CI DJ EG GQ ER SZ ET GA GM GH GN "
      "GW KE LS LR LY MG MW ML MR MU MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD "
      "TZ TG TN UG ZM ZW").split()

ASEAN = "BN KH ID LA MY MM PH SG TH VN".split()
GCC = "BH KW OM QA SA AE".split()
MERCOSUR = "AR BR PY UY BO".split()          # BO acceded 2024
ECOWAS = "BJ BF CV CI GM GH GN GW LR ML NE NG SN SL TG".split()

BLOCS = [
    ("EU27", EU27, "European Union (27)", "supranational_binding",
     "directives and regulations bind members; transposed into national law"),
    # NOT "AU": that is Australia's ISO-2 code, and a bloc code that collides
    # with a country code makes every AU member inherit Australia's rows.
    ("AFU", AU, "African Union", "intergovernmental",
     "continental strategy; targets implemented nationally"),
    ("ASEAN", ASEAN, "Association of Southeast Asian Nations", "intergovernmental",
     "APAEC energy cooperation targets; non-binding on members"),
    ("GCC", GCC, "Gulf Cooperation Council", "intergovernmental",
     "GCC Interconnection Authority; shared grid and market work"),
    ("MERCOSUR", MERCOSUR, "Mercosur", "intergovernmental",
     "customs union; limited energy competence"),
    ("ECOWAS", ECOWAS, "Economic Community of West African States", "intergovernmental",
     "ECOWAS renewable energy and efficiency policies (EREP/EEEP)"),
    ("UNFCCC", ["*"], "Paris Agreement / NDC framework", "global_instrument",
     "every party submits an NDC; the highest-yield source of a national "
     "economy-wide emissions target outside the EU"),
    ("IMO", ["*"], "International Maritime Organization", "global_sectoral",
     "international shipping only; excluded from country packs by default"),
    ("ICAO", ["*"], "ICAO / CORSIA", "global_sectoral",
     "international aviation only; excluded from country packs by default"),
]


def main():
    # A bloc code that is also an ISO-2 country code silently redirects every
    # member's query to that country's rows. Refuse to emit such a file.
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from countries import WORLD_SET
    clash = sorted({b for b, *_ in BLOCS} & WORLD_SET)
    if clash:
        raise SystemExit(f"ABORT: bloc code(s) collide with ISO-2 countries: {clash}")

    rows = []
    for bloc, members, name, kind, note in BLOCS:
        for m in members:
            rows.append({"bloc": bloc, "member": m, "bloc_name": name,
                         "kind": kind, "notes": note})
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print(f"blocs.csv: {len(rows)} memberships across {len(BLOCS)} blocs")
    for bloc, members, _, kind, _ in BLOCS:
        print(f"  {bloc:9} {len(members):3} member(s)  [{kind}]")


if __name__ == "__main__":
    main()
