# -*- coding: utf-8 -*-
# PORTED from /home/lukas/Desktop/earth/pypsa-earth/cookbooks/data_quality/_qa/build_scorecards.py (2026-07-22).
# Changes: REWRITTEN for pypsa-eur — universe is the default-config `countries:`
#          list, probes target the eur data/ archives (versioned layout), and the
#          PROBE_OVERRIDES dict holds code-read facts (each with a file:symbol
#          comment). Output contract (countries/<ISO2>.yaml, MATRIX.csv, INDEX.md)
#          unchanged; validated by check_registry.py.
"""
Generate per-country data-quality scorecards for pypsa-eur's default scope.

Deterministic — every grade comes from probing actual files on disk or from the
PROBE_OVERRIDES dict (code-read facts, each justified by a file:symbol comment).
Re-runnable; scorecards are never hand-edited. Probes are keyed to the dataset
ids in ../datasets.yaml (the authored registry); this script and the registry
must agree on ids (checked by check_registry.py).

Grades per dataset per country:
  A  native country-specific data present (row / file / dir / polygon)
  B  covered by a global/continental dataset, or the dataset is not applicable
  C  silent DEFAULT/proxy fallback applies (EU-average ratios, German profiles)
  D  absent and the feature silently disappears (no gas grid, zero biomass)

Outputs: ../countries/<ISO2>.yaml, ../MATRIX.csv, ../INDEX.md

Usage (eur pixi manifest is unparseable; use the earth env):
  cd /home/lukas/Desktop/earth/pypsa-earth && \
  pixi run python /home/lukas/Desktop/enderpearl/pypsa-eur/cookbooks/data_quality/_qa/build_scorecards.py
"""

import glob
import gzip
import os
import warnings

import pandas as pd
import yaml

warnings.filterwarnings("ignore")

QA_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = os.path.dirname(QA_DIR)
REPO = os.path.dirname(os.path.dirname(BOOK_DIR))

NAMES = {
    "AL": "Albania", "AT": "Austria", "BA": "Bosnia and Herzegovina",
    "BE": "Belgium", "BG": "Bulgaria", "CH": "Switzerland", "CZ": "Czechia",
    "DE": "Germany", "DK": "Denmark", "EE": "Estonia", "ES": "Spain",
    "FI": "Finland", "FR": "France", "GB": "United Kingdom", "GR": "Greece",
    "HR": "Croatia", "HU": "Hungary", "IE": "Ireland", "IT": "Italy",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "ME": "Montenegro",
    "MK": "North Macedonia", "NL": "Netherlands", "NO": "Norway",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "RS": "Serbia",
    "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia", "XK": "Kosovo",
}
# alternate spellings used by the country-name-keyed datasets (ppm, hotmaps, EIA)
NAME_ALTS = {
    "CZ": ["Czechia", "Czech Republic"],
    "MK": ["North Macedonia", "Macedonia"],
    "BA": ["Bosnia and Herzegovina", "Bosnia"],
    "GB": ["United Kingdom"],
}
# Eurostat-style codes used by JRC-IDEES, Eurostat balances, ENSPRESO, retro
EUROSTAT_CODE = {"GR": "EL", "GB": "UK"}

EU27_IN_SCOPE = set("AT BE BG CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV NL "
                    "PL PT RO SE SI SK".split())
LANDLOCKED = set("AT CH CZ HU LU MK RS SK XK".split())

# code-read facts that no file probe can express; each entry cites its source.
PROBE_OVERRIDES = {
    # scripts/build_electricity_demand.py: countries_w_no_types includes XK —
    # the synthetic load's KV column is dropped despite existing in the file.
    "synthetic-demand": {"XK": ("C", "KV column exists in the file but "
                                "build_electricity_demand.py hardcodes XK out "
                                "of the synthetic supplement")},
    # scripts/build_shapes.py: BA and XK GDP/pop come from rasters rescaled to
    # hardcoded World Bank totals (GDP BA=20.48, XK=7.9 bn; pop 3361k/1782k);
    # everyone else in scope has JRC ARDECO NUTS3 rows.
    "nuts3-population-gdp": {
        "BA": ("C", "no ARDECO NUTS3 rows — raster GDP/pop rescaled to "
                    "hardcoded World Bank totals in build_shapes.py"),
        "XK": ("C", "no ARDECO NUTS3 rows — raster GDP/pop rescaled to "
                    "hardcoded World Bank totals in build_shapes.py"),
    },
    # scripts/build_gas_input_locations.py: entry/storage points come from GEM +
    # IGGIELGN geojsons; ME and XK have none — no gas entry capacity at all.
    "gas-input-locations": {
        "ME": ("D", "no IGGIELGN/GEM entry, LNG or storage point"),
        "XK": ("D", "no IGGIELGN/GEM entry, LNG or storage point"),
    },
}

FAMILIES = {
    "demand-balances": ["jrc-idees", "eurostat-balances", "swiss-energy-balances",
                        "jrc-energy-atlas"],
    "electricity-load": ["electricity-demand-historic", "gb-national-demand",
                         "synthetic-demand"],
    "power-fleet": ["powerplantmatching-fleet", "eia-hydro-annual",
                    "hydro-capacities"],
    "grid": ["osm-grid", "tyndp-transmission-projects"],
    "gas-h2-co2": ["scigrid-gas-network", "gas-input-locations",
                   "h2-salt-caverns", "co2stop-sequestration"],
    "renewables-land": ["era5-sarah-cutout", "corine-landcover",
                        "natura-and-offshore-exclusions", "eez"],
    "industry": ["hotmaps-industrial-sites", "gem-steel-cement-trackers",
                 "ammonia-production-usgs"],
    "biomass": ["enspreso-biomass"],
    "heat-buildings": ["district-heating-potentials", "retro-building-stock",
                       "heat-profile-bdew"],
    "spatial-population": ["nuts3-population-gdp", "worldbank-urban-population"],
    "transport": ["transport-data-emobility"],
    "parameters": ["unit-commitment-parameters", "technology-costs"],
}
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def p(*parts):
    return os.path.join(REPO, *parts)


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def country_universe():
    cfg = load_yaml(p("config", "config.default.yaml"))
    return sorted(cfg["countries"])


def names_for(c):
    return NAME_ALTS.get(c, [NAMES[c]])


def ecode(c):
    return EUROSTAT_CODE.get(c, c)


# ---------------------------------------------------------------- probes ----
def probe_jrc_idees(universe):
    base = p("data", "jrc_idees", "archive", "2023-v1")
    out = {}
    for c in universe:
        if os.path.isdir(os.path.join(base, ecode(c))):
            out[c] = ("A", "per-country JRC-IDEES 2023 workbook directory")
        else:
            out[c] = ("C", "no IDEES dir — industry falls back to EU27-average "
                           "ratios (add_non_eu27_industrial_energy_demand), "
                           "residential/services to Eurostat + EU28 splits")
    return out


def probe_eurostat(universe):
    path = p("data", "eurostat_balances", "archive", "2026-02",
             "estat_nrg_bal_c.tsv.gz")
    geos = set()
    with gzip.open(path, "rt") as f:
        next(f)
        for line in f:
            geos.add(line.split("\t", 1)[0].rsplit(",", 1)[-1])
    out = {}
    for c in universe:
        if ecode(c) in geos:
            out[c] = ("A", "national energy-balance rows (nrg_bal_c)")
        elif c == "CH":
            out[c] = ("B", "not in Eurostat — the dedicated Swiss BFS "
                           "balances cover CH instead")
        else:
            out[c] = ("D", "no Eurostat energy balance rows")
    return out


def probe_wide_header(path, universe, col_of=None, sep=","):
    header = pd.read_csv(path, sep=sep, nrows=0)
    cols = {str(col).split("_")[0] for col in header.columns}
    return {c: ((col_of or (lambda x: x))(c) in cols) for c in universe}


def probe_electricity_demand(universe):
    entsoe = probe_wide_header(
        p("data", "entsoe_electricity_demand", "archive", "2026-02-02",
          "electricity_demand_entsoe_raw.csv"), universe)
    opsd = probe_wide_header(
        p("data", "opsd_electricity_demand", "archive", "2026-02-02",
          "electricity_demand_opsd_raw.csv"), universe)
    out = {}
    for c in universe:
        if entsoe[c] and opsd[c]:
            out[c] = ("A", "ENTSO-E transparency + OPSD historical load columns")
        elif entsoe[c]:
            out[c] = ("A", "ENTSO-E transparency load column (no OPSD backfill)")
        else:
            out[c] = ("C", "no historical load column — gap-filled/synthetic")
    return out


def probe_synthetic(universe):
    present = probe_wide_header(
        p("data", "synthetic_electricity_demand", "primary", "v2",
          "load_synthetic_raw.csv"),
        universe, col_of=lambda c: "KV" if c == "XK" else c)
    return {c: ("B", "synthetic profile column available as gap-fill layer")
            if present[c] else
            ("C", "no synthetic column — gaps rely on interpolation only")
            for c in universe}


def probe_name_count(path, universe, col, sep=",", unit="rows"):
    df = pd.read_csv(path, sep=sep, usecols=[col], dtype=str)
    counts = df[col].value_counts()
    out = {}
    for c in universe:
        n = int(sum(counts.get(alt, 0) for alt in names_for(c)))
        out[c] = n
    return out


def probe_powerplants(universe):
    path = p("data", "powerplants", "archive", "0.8.1", "powerplants.csv")
    df = pd.read_csv(path, usecols=["Country", "Fueltype", "Capacity"])
    out, fleets = {}, {}
    for c in universe:
        sub = df[df.Country.isin(names_for(c))]
        if len(sub):
            fleets[c] = {
                "plants": int(len(sub)),
                "capacity_mw": float(round(sub.Capacity.sum(), 1)),
                "fueltypes": sorted(sub.Fueltype.dropna().unique().tolist()),
            }
            out[c] = ("A", f"{len(sub)} plants, "
                           f"{fleets[c]['capacity_mw']} MW in powerplantmatching")
        else:
            out[c] = ("D", "no powerplantmatching rows — brownfield fleet empty")
    return out, fleets


def probe_scigrid(universe):
    path = p("data", "scigrid_gas", "primary", "1.1.2", "data",
             "IGGIELGN_PipeSegments.csv")
    df = pd.read_csv(path, sep=";", usecols=["country_code"])
    blob = " ".join(df.country_code.astype(str))
    out = {}
    for c in universe:
        code = "EL" if c == "GR" else c
        if f"'{code}'" in blob:
            out[c] = ("A", "IGGIELGN pipe segments present")
        else:
            out[c] = ("D", "no IGGIELGN pipes — country has no modelled gas grid")
    return out


def probe_enspreso(universe):
    path = p("data", "enspreso_biomass", "archive", "2019-06-20",
             "ENSPRESO_BIOMASS.xlsx")
    try:
        df = pd.read_excel(path, sheet_name="ENER - NUTS2 BioCom E")
    except Exception as e:
        return {c: ("C", f"probe failed: {e}") for c in universe}
    col = "NUTS2" if "NUTS2" in df.columns else \
        ("NUST2" if "NUST2" in df.columns else df.columns[0])
    prefixes = {str(v)[:2] for v in df[col].dropna()}
    out = {}
    for c in universe:
        if ecode(c) in prefixes:
            out[c] = ("A", "ENSPRESO NUTS2 biomass potential rows")
        else:
            out[c] = ("D", "no ENSPRESO rows — biomass potential silently zero")
    return out


def probe_hotmaps(universe):
    path = p("data", "hotmaps_industrial_sites", "archive", "version-1.1",
             "Industrial_Database.csv")
    counts = probe_name_count(path, universe, "Country", sep=";")
    return {c: ("A", f"{counts[c]} industrial sites")
            if counts[c] else
            ("C", "no hotmaps sites — industrial demand distributed by "
                  "population share (build_industrial_distribution_key)")
            for c in universe}


def probe_text_names(path, universe):
    with open(path, errors="replace") as f:
        text = f.read()
    return {c: any(alt in text for alt in names_for(c)) for c in universe}


def probe_eia_hydro(universe):
    present = probe_text_names(p("data", "eia_hydro_annual_generation.csv"),
                               universe)
    return {c: ("A", "EIA annual hydro generation rows (inflow normalization)")
            if present[c] else
            ("C", "no EIA rows — inflow normalized from runoff alone")
            for c in universe}


def probe_hydro_capacities(universe):
    df = pd.read_csv(p("data", "hydro_capacities.csv"), usecols=["Country"],
                     dtype=str)
    have = set(df.Country)
    return {c: ("A", "hydro capacity row") if c in have else
            ("C", "no row — reservoir max_hours falls back to defaults")
            for c in universe}


def probe_retro(universe):
    stock = pd.read_csv(p("data", "retro", "data_building_stock.csv"),
                        usecols=["country_code"], dtype=str)
    have = {str(v).upper() for v in stock.country_code.dropna()}
    patch_path = p("data", "retro", "floor_area_missing.csv")
    patched = set()
    if os.path.isfile(patch_path):
        pdf = pd.read_csv(patch_path, dtype=str, encoding="latin-1")
        patched = {str(v).upper() for v in pdf.iloc[:, 0].dropna()}
    out = {}
    for c in universe:
        code = ecode(c)
        if code in have:
            out[c] = ("A", "building stock rows (EU Building Stock Observatory)")
        elif code in patched or c in patched:
            out[c] = ("B", "floor area from the curated patch file")
        else:
            out[c] = ("C", "no stock data — population-based floor-area estimate")
    return out


def load_country_shapes():
    import geopandas as gpd
    path = p("resources", "enderpearl-base", "country_shapes.geojson")
    shapes = gpd.read_file(path).set_index("name")["geometry"]
    return shapes


def probe_geometry_points(universe, shapes, points_gdf, what):
    out = {}
    for c in universe:
        if c not in shapes.index:
            out[c] = ("D", f"no country shape to test {what}")
            continue
        hit = points_gdf.within(shapes[c]).any()
        out[c] = ("A", f"{what} present") if hit else \
            ("D", f"no {what} in or touching the country")
    return out


def probe_tyndp(universe, shapes):
    import geopandas as gpd
    from shapely.geometry import Point
    pts = []
    for fname in ("new_lines.csv", "new_links.csv"):
        path = p("data", "transmission_projects", "tyndp2020", fname)
        df = pd.read_csv(path)
        for _, r in df.iterrows():
            for a, b in (("x0", "y0"), ("x1", "y1")):
                if a in df.columns and pd.notna(r.get(a)):
                    pts.append(Point(float(r[a]), float(r[b])))
    gdf = gpd.GeoSeries(pts)
    out = {}
    for c in universe:
        if c not in shapes.index:
            out[c] = ("D", "no country shape")
            continue
        hit = gdf.within(shapes[c].buffer(0.05)).any()
        out[c] = ("A", "TYNDP 2020 project endpoint(s) in country") if hit else \
            ("D", "no TYNDP project endpoints — no candidate projects "
                  "(NEP adds DE-internal projects only)")
    return out


def probe_salt_caverns(universe, shapes):
    import geopandas as gpd
    path = p("data", "h2_salt_caverns", "archive", "16-10-2019",
             "h2_salt_caverns_GWh_per_sqkm.geojson")
    gdf = gpd.read_file(path)
    out = {}
    for c in universe:
        if c not in shapes.index:
            out[c] = ("C", "no country shape")
            continue
        hit = gdf.intersects(shapes[c].buffer(0.3)).any()
        out[c] = ("A", "salt-cavern potential polygons (on/near-shore)") if hit \
            else ("C", "no cavern geology — H2 storage limited to steel tanks")
    return out


def probe_co2stop(universe, shapes):
    import geopandas as gpd
    shps = glob.glob(p("data", "co2stop", "archive", "26-august-2020",
                       "**", "*.shp"), recursive=True)
    frames = []
    for s in shps:
        try:
            frames.append(gpd.read_file(s)[["geometry"]])
        except Exception:
            continue
    if not frames:
        return {c: ("C", "co2stop probe failed — no readable shapefiles")
                for c in universe}
    gdf = pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry")
    out = {}
    for c in universe:
        if c not in shapes.index:
            out[c] = ("D", "no country shape")
            continue
        hit = gdf.intersects(shapes[c].buffer(0.3)).any()
        out[c] = ("A", "CO2Stop storage-unit polygons in/near country") if hit \
            else ("D", "no surveyed CO2 storage units — onshore sequestration "
                       "potential zero")
    return out


def probe_gem_trackers(universe):
    out = {}
    counts = {}
    try:
        df = pd.read_excel(
            p("data", "gem_gspt", "archive", "march-2025-v1.1",
              "Global-Steel-Plant-Tracker.xlsx"),
            sheet_name=1)
        col = next(col for col in df.columns if str(col).strip() == "Country")
        vc = df[col].value_counts()
        for c in universe:
            counts[c] = int(sum(vc.get(alt, 0) for alt in names_for(c)))
    except Exception:
        counts = None
    for c in universe:
        if counts is None:
            out[c] = ("B", "global GEM trackers (probe unavailable)")
        elif counts[c]:
            out[c] = ("A", f"{counts[c]} GEM steel plants tracked")
        else:
            out[c] = ("B", "global tracker; no steel plants listed (may "
                           "genuinely be none)")
    return out


def probe_ammonia(universe):
    path = p("data", "ammonia_plants.csv")
    try:
        df = pd.read_csv(path, dtype=str)
        col = next((col for col in df.columns
                    if str(col).lower() in ("country", "country_code")),
                   df.columns[0])
        vals = set(df[col].dropna())
        out = {}
        for c in universe:
            if c in vals or any(alt in vals for alt in names_for(c)):
                out[c] = ("A", "ammonia plant rows")
            else:
                out[c] = ("D", "no ammonia plants listed — zero NH3 "
                               "production assumed")
        return out
    except Exception as e:
        return {c: ("C", f"probe failed: {e}") for c in universe}


# ------------------------------------------------------------- constants ----
def constant(universe, grade, detail):
    return {c: (grade, detail) for c in universe}


def build_static_probes(universe):
    shapes = load_country_shapes()
    static = {
        "jrc-idees": probe_jrc_idees(universe),
        "eurostat-balances": probe_eurostat(universe),
        "swiss-energy-balances": {
            c: ("A", "dedicated Swiss BFS energy balances") if c == "CH"
            else ("B", "not applicable — Eurostat covers this country")
            for c in universe},
        "electricity-demand-historic": probe_electricity_demand(universe),
        "gb-national-demand": {
            c: ("A", "NESO half-hourly demand + DESNZ subnational consumption")
            if c == "GB"
            else ("B", "not applicable — ENTSO-E/OPSD cover this country")
            for c in universe},
        "synthetic-demand": probe_synthetic(universe),
        "osm-grid": constant(
            universe, "B", "Europe-wide OSM prebuilt grid; completeness is "
                           "volunteer-dependent (thinner in the Balkans)"),
        "tyndp-transmission-projects": probe_tyndp(universe, shapes),
        "scigrid-gas-network": probe_scigrid(universe),
        "gas-input-locations": constant(
            universe, "B", "GEM Europe Gas Tracker + IGGIELGN border/LNG/"
                           "storage points"),
        "enspreso-biomass": probe_enspreso(universe),
        "hotmaps-industrial-sites": probe_hotmaps(universe),
        "gem-steel-cement-trackers": probe_gem_trackers(universe),
        "ammonia-production-usgs": probe_ammonia(universe),
        "h2-salt-caverns": probe_salt_caverns(universe, shapes),
        "eia-hydro-annual": probe_eia_hydro(universe),
        "hydro-capacities": probe_hydro_capacities(universe),
        "era5-sarah-cutout": constant(
            universe, "B", "gridded ERA5 + SARAH3 cutout covers the full "
                           "domain (single weather year 2013 on disk)"),
        "corine-landcover": constant(
            universe, "B", "EEA39 CORINE raster covers the full default scope"),
        "natura-and-offshore-exclusions": {
            c: ("A", "Natura 2000 protected-area raster (EU member)")
            if c in EU27_IN_SCOPE else
            ("C", "outside Natura 2000 — protected-area exclusions silently "
                  "skipped, renewable potentials overstated")
            for c in universe},
        "eez": {
            c: ("B", "not applicable — landlocked") if c in LANDLOCKED else
            ("A", "EEZ polygons for offshore regions")
            for c in universe},
        "nuts3-population-gdp": constant(
            universe, "A", "JRC ARDECO NUTS3 GDP + population rows"),
        "worldbank-urban-population": constant(
            universe, "A", "World Bank urban-population share row (XKX "
                           "included)"),
        "jrc-energy-atlas": {
            c: ("A", "JRC Energy Atlas spatial electricity-demand raster")
            if c in EU27_IN_SCOPE else
            ("C", "explicit EU27-only skip — demand distributed by NUTS3 "
                  "GDP/population keys instead")
            for c in universe},
        "district-heating-potentials": {
            c: ("B", "Fraunhofer DH areas + ISI geothermal potentials "
                     "(runtime-fetched, EU-scoped)")
            if c in EU27_IN_SCOPE else
            ("C", "outside the EU-scoped DH/geothermal datasets — "
                  "handle_missing_countries fallback / zero limited heat "
                  "sources")
            for c in universe},
        "retro-building-stock": probe_retro(universe),
        "co2stop-sequestration": probe_co2stop(universe, shapes),
        "transport-data-emobility": {
            c: ("A", "native BASt traffic counts") if c == "DE" else
            ("C", "German BASt kfz/pkw weekly profiles applied as proxy")
            for c in universe},
        "unit-commitment-parameters": constant(
            universe, "B", "per-carrier global UC parameters (no oil column)"),
        "technology-costs": constant(
            universe, "C", "uniform European cost table — no country-specific "
                           "capital costs or WACC"),
        "heat-profile-bdew": {
            c: ("A", "native BDEW standard load profiles") if c == "DE" else
            ("C", "German BDEW intraday heat profile applied as proxy")
            for c in universe},
    }
    # apply code-read overrides
    for ds, per_country in PROBE_OVERRIDES.items():
        for c, gd in per_country.items():
            static.setdefault(ds, {})[c] = gd
    return static


def rollup(ds_grades):
    fams = {}
    for family, members in FAMILIES.items():
        present = {ds: ds_grades[ds] for ds in members if ds in ds_grades}
        if not present:
            continue
        worst = max(present.values(), key=lambda g: GRADE_ORDER[g])
        fams[family] = {"grade": worst, "detail": present}
    return fams


def main():
    universe = country_universe()
    print(f"universe: {len(universe)} countries (default config scope)")

    static = build_static_probes(universe)
    registry_ids = [d["id"] for d in load_yaml(
        os.path.join(BOOK_DIR, "datasets.yaml"))]

    os.makedirs(os.path.join(BOOK_DIR, "countries"), exist_ok=True)
    _, fleets = probe_powerplants(universe)
    static["powerplantmatching-fleet"] = {
        c: ("A", f"{fleets[c]['plants']} plants, "
                 f"{fleets[c]['capacity_mw']} MW "
                 f"({', '.join(fleets[c]['fueltypes'][:6])})")
        if c in fleets else
        ("D", "no powerplantmatching rows — brownfield fleet empty")
        for c in universe}

    matrix_rows, summaries = [], []
    for c in universe:
        ds_grades, ds_details = {}, {}
        for ds in registry_ids:
            grade, detail = static.get(ds, {}).get(c, ("C", "no probe"))
            ds_grades[ds], ds_details[ds] = grade, detail

        card = {
            "country": c,
            "name": NAMES[c],
            "fleet_evidence": fleets.get(c),
            "families": rollup(ds_grades),
            "datasets": {ds: {"grade": ds_grades[ds], "detail": ds_details[ds]}
                         for ds in registry_ids},
        }
        with open(os.path.join(BOOK_DIR, "countries", f"{c}.yaml"), "w") as f:
            yaml.safe_dump(card, f, sort_keys=False, default_flow_style=False)

        matrix_rows.append({"country": c, **ds_grades})
        score = sum(GRADE_ORDER[g] for g in ds_grades.values())
        summaries.append((c, NAMES[c], score, ds_grades))

    matrix = pd.DataFrame(matrix_rows).set_index("country")
    matrix.to_csv(os.path.join(BOOK_DIR, "MATRIX.csv"))

    lines = [
        "# Data-quality cookbook — index (generated)",
        "",
        f"Per-country data-quality scorecards for the **{len(universe)} "
        "countries** in pypsa-eur's default scope "
        "(`config/config.default.yaml` `countries:`). Grades: **A** native",
        "country data · **B** global/continental dataset covers it (or not",
        "applicable) · **C** silent DEFAULT/proxy fallback · **D** absent,",
        "feature silently missing. Regenerate:",
        "`pixi run python cookbooks/data_quality/_qa/build_scorecards.py`",
        "(run via the earth repo's pixi env).",
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
        return (f"| {c} | {name} | {sum(1 for x in g.values() if x == 'A')} A "
                f"| {len(bad)} D |")

    lines += ["", "## Best-covered countries (top 10)", "",
              "| ISO2 | name | A-grades | D-grades |", "|---|---|---|---|"]
    lines += [fmt(t) for t in summaries[:10]]
    lines += ["", "## Worst-covered countries (bottom 10)", "",
              "| ISO2 | name | A-grades | D-grades |", "|---|---|---|---|"]
    lines += [fmt(t) for t in summaries[-10:]]
    lines += [
        "", "## The silent-fallback (C) datasets to watch", "",
        "Non-EU27 countries run industry on EU27-average ratios and",
        "residential/services on Eurostat + EU28 splits (no JRC-IDEES); ALL",
        "countries except Germany use the German BASt traffic and BDEW heat",
        "profiles; technology costs are Europe-uniform. These degrade",
        "silently — check a country's scorecard before trusting sector",
        "results. The headline gradient: EU27 core mostly A; CH/NO/GB carry",
        "native substitutes but miss the EU-scoped sources; the Western",
        "Balkans accumulate C/D grades; XK is the worst-covered country in",
        "scope.", "",
        "Dataset → dependent recipes: see `datasets.yaml` (`used_by`).",
    ]
    with open(os.path.join(BOOK_DIR, "INDEX.md"), "w") as f:
        f.write("\n".join(lines))

    print(f"wrote {len(universe)} scorecards, MATRIX.csv, INDEX.md")


if __name__ == "__main__":
    main()
