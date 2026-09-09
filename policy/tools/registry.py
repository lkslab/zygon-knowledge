#!/usr/bin/env python3
"""Query and validate the energy brockhaus (data/energy_brockhaus/).

The brockhaus is the interviewing agent's single reliable entry point for
national energy policy data worldwide: realized + planned assets, build-out and
carbon targets, subsidies, and regulation. This tool is the *only* sanctioned
query path: it resolves technology aliases, brackets milestone years, applies a
scenario preference, attaches the model carrier, and reports coverage so the
agent can tell "no target exists" from "not collected yet".

Stdlib only -- no pandas, no env activation, runs anywhere python3 does.

Usage:
  python3 tools/registry.py pack  --country NG --year 2030
  python3 tools/registry.py query --country EU --type targets --tech solar
  python3 tools/registry.py query --country DE --year 2035 --type targets --tech wind_offshore
  python3 tools/registry.py validate

Add --json for machine-readable output (default for `pack`).
"""
import argparse
import csv
import json
import sys
from collections import OrderedDict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TABLES = ["assets", "targets", "subsidies", "regulation"]

# Legacy aliases for the EU bloc. blocs.csv is the real membership table; these
# two codes appear as `country` values on ~32 union-level rows.
EU_CODES = {"EU", "EU27"}

# Which bloc kinds are unioned into a member state's query by default.
# global_sectoral (IMO shipping, ICAO aviation) is opt-in via --bloc: an
# international shipping target is not a national energy target.
UNION_KINDS = {"supranational_binding", "intergovernmental", "global_instrument"}

# Lower rank = preferred when several scenarios describe the same target.
# A directly-cited national plan/law outranks Ember's older NECP projections, so
# the most recent authoritative figure wins by default (override with --scenario).
SCEN_RANK = {
    "legislated": 0, "binding": 0, "adopted": 1,
    "ndc": 1,                                   # communicated to the UNFCCC: a formal
                                                # commitment, but not domestic law, so
                                                # it loses to a statute and beats a
                                                # press announcement
    "announced": 2, "planned": 2,               # national plans (e.g. revised NECP)
    "lts": 2,                                   # long-term strategy: political, like
                                                # `announced`
    "wam": 3, "wem": 4, "projection": 5,        # Ember NECP scenario trajectories
    "proposed": 6, "indicative": 6,
}


def load(name):
    """Every value a string, missing keys empty -- mirrors the old
    pd.read_csv(dtype=str, keep_default_na=False).fillna("")."""
    with open(BASE / f"{name}.csv", newline="", encoding="utf-8") as f:
        return [{k: (v if v is not None else "") for k, v in row.items()}
                for row in csv.DictReader(f)]


def columns(name):
    with open(BASE / f"{name}.csv", newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def taxonomy():
    return load("technology_taxonomy")


def alias_map(tax):
    m = {}
    for r in tax:
        canon = r["technology"].strip()
        m[canon.lower()] = canon
        for a in str(r["aliases"]).split(";"):
            a = a.strip().lower()
            if a:
                m[a] = canon
    return m


def resolve_tech(tech, amap):
    if not tech:
        return None
    return amap.get(tech.strip().lower(), tech)


def tech_group(tech, tax):
    for r in tax:
        if r["technology"].lower() == str(tech).lower():
            return r["group"]
    return ""


def to_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def coverage_status(country, rtype, tech, cov, tax):
    grp = tech_group(tech, tax) if tech else ""
    sub = [r for r in cov if r["record_type"] == rtype and r["country"] == country]
    if grp:
        g = [r for r in sub if r["technology_group"] == grp]
        if g:
            return g[0]["completeness"]
    if sub:
        return sub[0]["completeness"]
    return "missing"


def blocs_for(country, extra=()):
    """The bloc codes whose rows apply to `country`, mapped to their bloc name.

    Returns {} for a country in no bloc -- which is the fix for the bug where
    every country on earth inherited the EU's directives. `extra` force-includes
    a bloc whose kind is not unioned by default (--bloc IMO)."""
    path = BASE / "blocs.csv"
    if not path.exists():
        return {}
    out = {}
    for r in load("blocs"):
        if r["member"] not in (country, "*"):
            continue
        if r["kind"] in UNION_KINDS or r["bloc"] in extra:
            out[r["bloc"]] = r["bloc_name"]
    # `EU` and `EU27` are both used as country codes on union-level rows.
    if "EU27" in out:
        out["EU"] = out["EU27"]
    return out


def country_filter(rows, country, include_blocs, extra_blocs=()):
    """Keep the country's own rows, plus the rows of every bloc it belongs to.

    Preserves table order (a boolean mask, not a concatenation) -- downstream
    grouping is first-appearance ordered, so row order is load-bearing.

    Inherited rows are tagged `_via` with the bloc name. Without it a pack
    cannot distinguish "Germany's target" from "the EU target that applies to
    Germany", which is exactly the confusion that let EU rows sit unremarked in
    a Nigerian pack."""
    blocs = blocs_for(country, extra_blocs) if include_blocs else {}
    out = []
    for r in rows:
        if r["country"] == country:
            out.append(r)
        elif r["country"] in blocs:
            out.append(dict(r, _via=blocs[r["country"]]))
    return out


def scen_rank(s):
    return SCEN_RANK.get(str(s).strip().lower(), 5)


def select_targets(rows, year, scenario):
    """Per (country, technology, metric, unit, basis) group: pick the requested
    scenario (or best-ranked), then the exact year, else bracket the year.

    `basis` is in the key because two percentages with different denominators
    are not the same target -- a 40%-of-generation and a 40%-of-final-energy
    row must not out-rank each other. `scope_note` is deliberately NOT in the
    key: it is prose, and grouping on it would re-fragment the groups the way
    free-text units used to."""
    if scenario:
        rows = [r for r in rows if r["scenario"].lower() == scenario.lower()]
    out = []
    keys = ["country", "technology", "metric", "unit", "basis"]
    groups = OrderedDict()
    for r in rows:
        groups.setdefault(tuple(r[k] for k in keys), []).append(r)
    for g in groups.values():
        if not scenario:
            best = min(scen_rank(r["scenario"]) for r in g)
            g = [r for r in g if scen_rank(r["scenario"]) == best]
        if year is None:
            out.extend(dict(r, _flag="") for r in g)
            continue
        ys = [(to_int(r["year"]), r) for r in g]
        exact = [r for y, r in ys if y == year]
        if exact:
            out.extend(dict(r, _flag="exact") for r in exact)
            continue
        below = sorted([(y, r) for y, r in ys if y is not None and y < year],
                       key=lambda t: t[0])
        above = sorted([(y, r) for y, r in ys if y is not None and y > year],
                       key=lambda t: t[0])
        bracket = ([below[-1][1]] if below else []) + ([above[0][1]] if above else [])
        out.extend(dict(r, _flag="nearest") for r in bracket)
    return out


def active_in_year(rows, year, start_col, end_col):
    if year is None:
        return rows
    keep = []
    for r in rows:
        s, e = to_int(r.get(start_col)), to_int(r.get(end_col))
        if (s is None or s <= year) and (e is None or e >= year):
            keep.append(r)
    return keep


def run_query(rtype, country, year, tech, scenario, include_blocs, amap, tax,
              extra_blocs=()):
    rows = country_filter(load(rtype), country, include_blocs, extra_blocs)
    if tech:
        rows = [r for r in rows if r["technology"].lower() == tech.lower()]
    if rtype == "targets":
        return select_targets(rows, year, scenario)
    if rtype == "assets":
        rows = active_in_year(rows, year, "year", "retire_year")
    elif rtype == "subsidies":
        rows = active_in_year(rows, year, "year_start", "year_end")
    elif rtype == "regulation":
        rows = active_in_year(rows, year, "year", "sunset_year")
    return [dict(r, _flag="") for r in rows]


def cmd_query(a):
    tax = taxonomy()
    amap = alias_map(tax)
    tech = resolve_tech(a.tech, amap) if a.tech else None
    types = [a.type] if a.type else TABLES
    rows = []
    for t in types:
        rows.extend(run_query(t, a.country, a.year, tech, a.scenario,
                              not a.no_blocs, amap, tax, tuple(a.bloc or ())))
    if a.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        _print_rows(rows)


def cmd_pack(a):
    tax = taxonomy()
    amap = alias_map(tax)
    cov = load("coverage")
    year = a.year
    xb = tuple(a.bloc or ())
    tgt = run_query("targets", a.country, year, None, a.scenario, True, amap, tax, xb)
    sections = {
        "targets": [r for r in tgt if r.get("metric") != "emissions"],
        "carbon": [r for r in tgt if r.get("metric") == "emissions"],
        "assets": run_query("assets", a.country, year, None, None, True, amap, tax, xb),
        "subsidies": run_query("subsidies", a.country, year, None, None, True, amap, tax, xb),
        "regulation": run_query("regulation", a.country, year, None, None, True, amap, tax, xb),
    }
    pack = {
        "country": a.country,
        "year": year,
        "coverage": {
            rt: coverage_status(a.country, "targets" if rt == "carbon" else rt,
                                None, cov, tax)
            for rt in sections
        },
    }
    pack.update(sections)
    print(json.dumps(pack, indent=2, ensure_ascii=False))


def _print_rows(rows):
    if not rows:
        print("(no matching records)")
        return
    for r in rows:
        val = r.get("value") or r.get("capacity_value") or ""
        unit = r.get("unit") or r.get("capacity_unit") or ""
        flag = f" [{r['_flag']}]" if r.get("_flag") else ""
        print(f"{r['record_id']:42} {r['country']:4} {r['technology']:14} "
              f"{val:>8} {unit:18} {r.get('year',''):>6}{flag}")


def cmd_validate(a):
    tax = taxonomy()
    valid_tech = {r["technology"].lower() for r in tax}
    carrier = {r["technology"].lower(): r["model_carrier"] for r in tax}
    errors = []
    seen_ids = {}
    for t in TABLES:
        rows = load(t)
        cols = set(columns(t))
        for i, r in enumerate(rows):
            rid = r.get("record_id", "")
            loc = f"{t}.csv:{rid or i}"
            if not rid:
                errors.append(f"{loc}: missing record_id")
            elif rid in seen_ids:
                errors.append(f"{loc}: duplicate record_id (also {seen_ids[rid]})")
            else:
                seen_ids[rid] = loc
            req = ["country", "technology", "source_url", "retrieved"]
            if t != "assets":
                req.append("year")  # assets may be historical or undated-planned
            for col in req:
                if col in cols and not str(r.get(col, "")).strip():
                    errors.append(f"{loc}: empty required field '{col}'")
            tk = str(r.get("technology", "")).lower()
            if tk and tk not in valid_tech:
                errors.append(f"{loc}: technology '{r['technology']}' not in taxonomy")
            elif tk and str(r.get("model_carrier", "")) != str(carrier.get(tk, "")):
                errors.append(f"{loc}: model_carrier '{r.get('model_carrier')}' "
                              f"!= taxonomy '{carrier.get(tk)}'")
            for yc in ("year", "retire_year", "baseline_year"):
                yv = to_int(r.get(yc))
                if yv is not None and not (1900 <= yv <= 2100):  # plants outlive 2050
                    errors.append(f"{loc}: {yc} {yv} outside [1900, 2100]")
    if errors:
        print(f"FAIL ({len(errors)} issue(s)):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print("OK: all brockhaus tables valid")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="filter records by country/year/technology/type")
    q.add_argument("--country", required=True, help="ISO-2 code or EU")
    q.add_argument("--year", type=int, help="query year (brackets milestone targets)")
    q.add_argument("--tech", help="technology (aliases resolved via taxonomy)")
    q.add_argument("--type", choices=TABLES, help="restrict to one table")
    q.add_argument("--scenario", help="force a scenario (else best-ranked wins)")
    q.add_argument("--no-blocs", "--no-eu", action="store_true", dest="no_blocs",
                   help="exclude bloc-level rows (--no-eu is the legacy spelling)")
    q.add_argument("--bloc", action="append", metavar="CODE",
                   help="force-include a bloc excluded by default (e.g. IMO, ICAO)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_query)

    pk = sub.add_parser("pack", help="full per-(country,year) bundle as JSON")
    pk.add_argument("--country", required=True)
    pk.add_argument("--year", type=int, required=True)
    pk.add_argument("--scenario")
    pk.add_argument("--bloc", action="append", metavar="CODE",
                    help="force-include a bloc excluded by default (e.g. IMO, ICAO)")
    pk.set_defaults(func=cmd_pack)

    v = sub.add_parser("validate", help="schema / provenance / taxonomy checks")
    v.set_defaults(func=cmd_validate)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
