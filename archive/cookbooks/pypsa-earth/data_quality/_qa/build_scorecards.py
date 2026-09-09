# -*- coding: utf-8 -*-
"""
Generate per-country data-quality scorecards (ex-Europe) for pypsa-earth.

Deterministic — every grade comes from probing actual files on disk (static
probes) or already-built networks/resources (build-derived probes). Re-runnable;
scorecards are never hand-edited. Probes are keyed to the dataset ids in
../datasets.yaml (the authored registry); this script and the registry must
agree on ids (checked by check_registry.py).

Grades per dataset per country:
  A  native country-specific data present (row / file / cached extract)
  B  covered by a global dataset or derivable (global GADM, UNSD row, raster)
  C  silent DEFAULT/proxy fallback applies (demand CAGRs, German profiles)
  D  absent and the feature silently disappears (caverns, plants, AL)

Outputs: ../countries/<ISO2>.yaml, ../MATRIX.csv, ../INDEX.md

Usage: pixi run python cookbooks/data_quality/_qa/build_scorecards.py
"""

import glob
import os
import sys
import warnings
from collections import defaultdict

import pandas as pd
import yaml

warnings.filterwarnings("ignore")

QA_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = os.path.dirname(QA_DIR)
REPO = os.path.dirname(os.path.dirname(BOOK_DIR))
sys.path.insert(0, os.path.join(REPO, "scripts"))

from stage_gadm_from_global import iso2_to_iso3  # noqa: E402

EUROPE = set(
    "AD AL AT BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT "
    "LU LV MC MD ME MK MT NL NO PL PT RO RS SE SI SK SM UA VA XK".split()
)

FAMILIES = {
    "shapes": ["gadm-boundaries", "worldpop-population", "gdp-raster"],
    "grid": ["osm-grid"],
    "climate": ["era5-cutout", "global-gis-layers"],
    "power-fleet": ["powerplant-fleet", "hydro-capacities", "eia-hydro-generation"],
    "electricity-demand": ["electricity-demand-forecast"],
    "sector-demand": [
        "unsd-energy-balances", "demand-growth-cagr", "demand-efficiency-cagr",
        "fuel-shares", "district-heating-share", "german-traffic-proxy",
        "bdew-heat-proxy",
    ],
    "industry": [
        "industry-growth-cagr", "industrial-plant-database", "ammonia-plants",
        "al-production",
    ],
    "hydrogen": ["salt-cavern-potentials"],
}

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def p(*parts):
    return os.path.join(REPO, *parts)


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- universe ----
def country_universe():
    cfg = load_yaml(p("configs", "regions_definition_config.yaml"))
    world_iso = cfg["world_iso"]
    continent_of, name_of = {}, {}
    for continent, countries in world_iso.items():
        for iso2, gname in countries.items():
            continent_of[iso2] = continent
            name_of[iso2] = gname
    universe = sorted(c for c in continent_of if c not in EUROPE)
    return universe, continent_of, name_of, cfg.get("iso_to_geofk_dict", {})


# ------------------------------------------------------------ static probes ---
def csv_countries(path, col=0):
    df = pd.read_csv(path)
    return set(df.iloc[:, col].astype(str).str.strip()) if len(df) else set()


def csv_column_countries(path, colname):
    df = pd.read_csv(path)
    return set(df[colname].astype(str).str.strip()) if colname in df else set()


def unsd_iso2_set():
    """All ISO2 codes appearing in the cached UNSD txt files (name-matched)."""
    import country_converter as coco

    names = set()
    for path in glob.glob(p("data", "demand", "unsd", "data", "*.txt")):
        try:
            df = pd.read_csv(path, sep=";", usecols=[0], quotechar='"')
            names.update(df.iloc[:, 0].astype(str).str.strip())
        except Exception:
            continue
    names.discard("Country or Area")
    cc = coco.CountryConverter()
    converted = cc.convert(names=sorted(names), to="ISO2", not_found=None)
    if isinstance(converted, str):
        converted = [converted]
    return {c for c in converted if isinstance(c, str) and len(c) == 2}


def build_static_probes(universe, continent_of, name_of, geofk):
    """Return {dataset_id: {iso2: (grade, detail)}} for the static datasets."""
    grades = defaultdict(dict)

    # 5 demand CSVs: row -> A, else C (DEFAULT fallback)
    for ds, fname in [
        ("demand-growth-cagr", "growth_factors_cagr.csv"),
        ("demand-efficiency-cagr", "efficiency_gains_cagr.csv"),
        ("industry-growth-cagr", "industry_growth_cagr.csv"),
        ("fuel-shares", "fuel_shares.csv"),
        ("district-heating-share", "district_heating.csv"),
    ]:
        present = csv_countries(p("data", "demand", fname))
        for c in universe:
            grades[ds][c] = ("A", "country row") if c in present \
                else ("C", "DEFAULT row fallback")

    # silent-zero csv datasets: row -> A, else D
    for ds, path, col in [
        ("salt-cavern-potentials", p("data", "hydrogen_salt_cavern_potentials.csv"), "ct"),
        ("al-production", p("data", "AL_production.csv"), "country"),
        ("industrial-plant-database", p("resources", "industrial_database.csv"), "country"),
        ("ammonia-plants", p("resources", "ammonia_plants.csv"), "country"),
    ]:
        present = csv_column_countries(path, col) if os.path.isfile(path) else set()
        for c in universe:
            grades[ds][c] = ("A", "country row(s)") if c in present \
                else ("D", "no row — feature silently absent/zero")

    # hydro capacities: row -> A, else C — NOT D: attach_hydro only derives
    # reservoir max_hours from this file (missing -> logged warning + 6h default);
    # plant MW comes from powerplantmatching, inflow normalization from IRENA
    hydro_present = csv_column_countries(p("data", "hydro_capacities.csv"), "Country")
    for c in universe:
        grades["hydro-capacities"][c] = ("A", "country row") if c in hydro_present \
            else ("C", "reservoir max_hours falls back to 6h default; "
                       "capacity and inflow unaffected")

    # EIA hydro: country names -> A else D
    eia = p("data", "eia_hydro_annual_generation.csv")
    eia_iso2 = set()
    if os.path.isfile(eia):
        import country_converter as coco
        raw = pd.read_csv(eia, skiprows=1).iloc[:, 1].dropna().astype(str)
        conv = coco.CountryConverter().convert(
            names=sorted(set(raw.str.strip())), to="ISO2", not_found=None)
        if isinstance(conv, str):
            conv = [conv]
        eia_iso2 = {x for x in conv if isinstance(x, str) and len(x) == 2}
    for c in universe:
        grades["eia-hydro-generation"][c] = ("A", "country row") if c in eia_iso2 \
            else ("D", "no row — hydro normalization falls back")

    # UNSD: name present -> B (global dataset), else D
    unsd = unsd_iso2_set()
    for c in universe:
        grades["unsd-energy-balances"][c] = ("B", "in cached UNSD extract") if c in unsd \
            else ("D", "not matched in UNSD files — sector totals NaN")

    # GADM: sliced dir -> A; global gpkg -> B
    has_global_gadm = os.path.isfile(p("data", "gadm", "gadm_410.gpkg"))
    for c in universe:
        iso3 = iso2_to_iso3([c]).get(c)
        sliced = iso3 and os.path.isfile(
            p("data", "gadm", f"gadm41_{iso3}", f"gadm41_{iso3}.gpkg"))
        grades["gadm-boundaries"][c] = ("A", f"sliced gadm41_{iso3}") if sliced \
            else ("B", "derivable from global gadm_410.gpkg") if has_global_gadm \
            else ("C", "must download (server unreliable)")

    # OSM: own pbf cached -> A; mapped into another extract or downloadable -> B
    for c in universe:
        gname = name_of.get(c, "").replace(" ", "-")
        own = os.path.isfile(p("data", "osm", "pbf", f"{gname}-latest.osm.pbf"))
        if own:
            grades["osm-grid"][c] = ("A", f"cached {gname}-latest.osm.pbf")
        elif c in geofk:
            grades["osm-grid"][c] = ("B", f"served by extract '{geofk[c]}'")
        else:
            grades["osm-grid"][c] = ("B", "downloadable from geofabrik")

    # WorldPop: tif cached -> A else B (per-country API retrieval)
    for c in universe:
        iso3 = (iso2_to_iso3([c]).get(c) or "").lower()
        tif = iso3 and os.path.isfile(
            p("data", "WorldPop", f"{iso3}_ppp_2020_UNadj_constrained.tif"))
        grades["worldpop-population"][c] = ("A", "cached tif") if tif \
            else ("B", "retrieved per-country at build time")

    # GDP raster / global GIS: global gridded -> B if file present
    gdp_ok = os.path.isfile(p("data", "GDP", "GDP_PPP_1990_2015_5arcmin_v2.nc"))
    gis_ok = os.path.isfile(p("data", "natura", "natura.tiff"))
    for c in universe:
        grades["gdp-raster"][c] = ("B", "global raster") if gdp_ok else ("C", "not on disk")
        grades["global-gis-layers"][c] = ("B", "global layers on disk") if gis_ok \
            else ("C", "not on disk")

    # cutout: continent file on disk -> A else C (buildable via CDS)
    continent_cutout = {
        "Africa": "africa", "Asia": "asia", "NorthAmerica": "northamerica",
        "SouthAmerica": "southamerica", "Oceania": "oceania",
    }
    for c in universe:
        cont = continent_of.get(c)
        key = continent_cutout.get(cont)
        f = key and os.path.isfile(p("cutouts", f"cutout-2013-era5-{key}.nc"))
        grades["era5-cutout"][c] = ("A", f"cutout-2013-era5-{key}.nc on disk") if f \
            else ("C", "no prebuilt cutout on disk — build via CDS or stage bundle")

    # electricity demand forecast: SSP continent file or demandcast parquet -> B
    demandcast = os.path.isfile(
        p("data", "demand", "forecasts_on_historical_period.parquet"))
    for c in universe:
        cont = continent_of.get(c)
        ssp = cont and os.path.isfile(
            p("data", "ssp2-2.6", "2030", "era5_2013", f"{cont}.nc"))
        if ssp or demandcast:
            src = "GEGIS ssp2 continent file" if ssp else "demandcast parquet"
            grades["electricity-demand-forecast"][c] = ("B", src)
        else:
            grades["electricity-demand-forecast"][c] = ("C", "forecast data not on disk")

    # proxies: always C — the point is that they are NOT country-specific
    for c in universe:
        grades["german-traffic-proxy"][c] = (
            "C", "German weekly traffic counts applied globally")
        grades["bdew-heat-proxy"][c] = (
            "C", "German BDEW heat profile applied globally")

    # powerplant fleet: default B (global PPM), refined by build evidence later
    for c in universe:
        grades["powerplant-fleet"][c] = ("B", "powerplantmatching global DB (unverified)")

    return grades


# ----------------------------------------------------- build-derived probes ---
def build_evidence(universe):
    """Mine networks/<run>/base.nc + resources/<run>/powerplants.csv."""
    import pypsa

    evidence = {}
    for base in sorted(glob.glob(p("networks", "*", "base.nc"))):
        run = os.path.basename(os.path.dirname(base))
        try:
            n = pypsa.Network(base)
            n.determine_network_topology()
        except Exception:
            continue
        buses = n.buses
        if "country" not in buses or not len(buses):
            continue
        line_country = n.lines.bus0.map(buses.country) if len(n.lines) else pd.Series(dtype=str)
        for c, sub in buses.groupby("country"):
            if c not in universe:
                continue
            comp_sizes = sub.sub_network.value_counts()
            rec = {
                "region": run,
                "base_buses": int(len(sub)),
                "base_lines": int((line_country == c).sum()),
                "ac_islands_touching": int(sub.sub_network.nunique()),
                "largest_component_share": round(float(comp_sizes.iloc[0] / len(sub)), 3),
            }
            old = evidence.get(c)
            if old is None or rec["base_buses"] > old["base_buses"]:
                evidence[c] = rec

    fleets = {}
    for ppl in sorted(glob.glob(p("resources", "*", "powerplants.csv"))):
        try:
            df = pd.read_csv(ppl, usecols=["Country", "Fueltype", "Capacity"])
        except Exception:
            continue
        for c, sub in df.groupby("Country"):
            if c not in universe:
                continue
            rec = {
                "plants": int(len(sub)),
                "capacity_mw": round(float(sub.Capacity.sum()), 1),
                "fueltypes": sorted(sub.Fueltype.dropna().unique().tolist()),
                "source_run": os.path.basename(os.path.dirname(ppl)),
            }
            old = fleets.get(c)
            if old is None or rec["plants"] > old["plants"]:
                fleets[c] = rec
    return evidence, fleets


# ------------------------------------------------------------------ output ----
def rollup(dataset_grades):
    fam = {}
    for family, members in FAMILIES.items():
        graded = {m: dataset_grades[m] for m in members if m in dataset_grades}
        if not graded:
            continue
        worst = max(graded.values(), key=lambda g: GRADE_ORDER[g])
        fam[family] = {"grade": worst, "detail": graded}
    return fam


def main():
    universe, continent_of, name_of, geofk = country_universe()
    print(f"universe: {len(universe)} countries (ex-Europe)")

    static = build_static_probes(universe, continent_of, name_of, geofk)
    evidence, fleets = build_evidence(universe)
    print(f"build evidence: {len(evidence)} countries (grid), {len(fleets)} (fleet)")

    registry_ids = [d["id"] for d in load_yaml(os.path.join(BOOK_DIR, "datasets.yaml"))] \
        if os.path.isfile(os.path.join(BOOK_DIR, "datasets.yaml")) else sorted(static)

    os.makedirs(os.path.join(BOOK_DIR, "countries"), exist_ok=True)
    matrix_rows = []
    summaries = []
    for c in universe:
        ds_grades, ds_details = {}, {}
        for ds in registry_ids:
            grade, detail = static.get(ds, {}).get(c, ("C", "no probe"))
            ds_grades[ds], ds_details[ds] = grade, detail

        # refine fleet grade with build evidence
        if c in fleets:
            f = fleets[c]
            ds_grades["powerplant-fleet"] = "A" if f["plants"] > 0 else "D"
            ds_details["powerplant-fleet"] = (
                f"{f['plants']} plants, {f['capacity_mw']} MW "
                f"({', '.join(f['fueltypes'][:6])}) [run {f['source_run']}]")

        card = {
            "country": c,
            "name": name_of.get(c, c),
            "continent": continent_of.get(c),
            "build_evidence": evidence.get(c),
            "fleet_evidence": fleets.get(c),
            "families": {},
            "datasets": {ds: {"grade": ds_grades[ds], "detail": ds_details[ds]}
                         for ds in registry_ids},
        }
        for family, info in rollup(ds_grades).items():
            entry = dict(info)
            if family == "grid" and evidence.get(c):
                ev = evidence[c]
                entry["fragmentation"] = (
                    f"{ev['ac_islands_touching']} AC islands touch {c}; largest "
                    f"in-country component holds {ev['largest_component_share']:.0%} "
                    f"of its {ev['base_buses']} buses [region {ev['region']}]")
            card["families"][family] = entry

        with open(os.path.join(BOOK_DIR, "countries", f"{c}.yaml"), "w") as f:
            yaml.safe_dump(card, f, sort_keys=False, default_flow_style=False)

        matrix_rows.append({"country": c, **ds_grades})
        score = sum(GRADE_ORDER[g] for g in ds_grades.values())
        summaries.append((c, name_of.get(c, c), score, ds_grades))

    matrix = pd.DataFrame(matrix_rows).set_index("country")
    matrix.to_csv(os.path.join(BOOK_DIR, "MATRIX.csv"))

    # INDEX.md
    lines = [
        "# Data-quality cookbook — index (generated)",
        "",
        f"Per-country data-quality scorecards for **{len(universe)} countries**",
        "(all of `world_iso` excluding Europe — Europe is covered by a different",
        "PyPSA model). Grades: **A** native country data · **B** global dataset",
        "covers it · **C** silent DEFAULT/proxy fallback · **D** absent, feature",
        "silently missing. Regenerate: `pixi run python",
        "cookbooks/data_quality/_qa/build_scorecards.py`.",
        "",
        f"Build-derived grid evidence available for **{len(evidence)}** countries",
        f"(from {len(set(e['region'] for e in evidence.values()))} built runs);",
        f"fleet evidence for **{len(fleets)}**.",
        "",
        "## Grade distribution per dataset",
        "",
        "| dataset | A | B | C | D |",
        "|---|---|---|---|---|",
    ]
    for ds in registry_ids:
        counts = matrix[ds].value_counts()
        lines.append(
            f"| {ds} | {counts.get('A', 0)} | {counts.get('B', 0)} "
            f"| {counts.get('C', 0)} | {counts.get('D', 0)} |")

    summaries.sort(key=lambda t: t[2])
    def fmt(t):
        c, name, score, g = t
        bad = [ds for ds, gr in g.items() if gr == "D"]
        return f"| {c} | {name} | {sum(1 for x in g.values() if x=='A')} A | {len(bad)} D |"
    lines += ["", "## Best-covered countries (top 10)", "",
              "| ISO2 | name | A-grades | D-grades |", "|---|---|---|---|"]
    lines += [fmt(t) for t in summaries[:10]]
    lines += ["", "## Worst-covered countries (bottom 10)", "",
              "| ISO2 | name | A-grades | D-grades |", "|---|---|---|---|"]
    lines += [fmt(t) for t in summaries[-10:]]
    lines += [
        "", "## The silent-fallback (C) datasets to watch", "",
        "Countries without native rows in the demand CAGR/fuel-share CSVs run on",
        "the DEFAULT row; ALL countries use the German traffic and BDEW heat",
        "profiles. These degrade silently — check a country's scorecard before",
        "trusting sector-demand results.", "",
        "Dataset → dependent recipes: see `datasets.yaml` (`used_by`).",
    ]
    with open(os.path.join(BOOK_DIR, "INDEX.md"), "w") as f:
        f.write("\n".join(lines))

    print(f"wrote {len(universe)} scorecards, MATRIX.csv, INDEX.md")


if __name__ == "__main__":
    main()
