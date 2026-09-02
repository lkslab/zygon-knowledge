# -*- coding: utf-8 -*-
"""
Shared core for the topic-card QA. The two per-model entry points

    cookbooks/pypsa-eur/topics/_qa/check_topics.py
    cookbooks/pypsa-earth/topics/_qa/check_topics.py

are thin drivers over this module; they differ only in EXPECTED_MODEL and
EXPECTED_REF_PREFIX. Before 2026-08-02 the whole checker was duplicated in both
places (eur PORTED from earth) with the TOPICS dict copied verbatim — that dict
IS the canonical Appendix A universe shared by both suites, so it lives here now
and is edited once.

Checks:
  1. FUNCTIONALITY.yaml: parses, ids unique, status in vocab, consumer is
     file:symbol with the symbol verbatim in the file (grep -F semantics),
     no URLs/line numbers; consumer required unless status is 'absent'
  2. exactly one card per canonical Appendix A topic (rank<->slug<->title
     bijection pinned in TOPICS below); no stray yaml files
  3. each card: required keys, id==stem kebab, rank matches, coverage in
     {ready, partial, gap}, when_to_use non-empty list, single model section
     anchored at the expected submodule ref
  4. every recipes.generation_conversion / recipes.demand slug exists in the
     respective book
  5. GENERATION SPLIT (2026-08-02). A card carrying `schema_version: 2` has
     MIGRATED: it links executable method specs (`methods:`) instead of
     capability-registry ids (`functionality:`), and it is the only kind of
     card that may scope a study — see cookbooks/_qa/TOPIC_CARD.schema.yaml.
     v1 cards keep their old validation unchanged; they are still the live
     routing surface for every unmigrated topic, so they are never skipped.

Normative field reference: cookbooks/_qa/TOPIC_CARD.schema.yaml
Authoring template:        cookbooks/_qa/TOPIC_CARD.template.yaml
"""

import argparse
import glob
import os
import re
import sys

import yaml

STATUS_VOCAB = {"working", "partial", "dead-key", "absent"}
COVERAGE_VOCAB = {"ready", "partial", "gap"}
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PLOT_ID_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")  # plot cards are snake_case
LINENO_RE = re.compile(r"(:\d+\s*$|#L\d+)")

# keys every card carries, whatever its generation
COMMON_KEYS = ("id", "title", "rank", "question", "when_to_use", "recipes",
               "gap_assessment", "coverage", "models")
V1_ONLY_KEYS = ("functionality",)
V2_ONLY_KEYS = ("schema_version", "methods")

# canonical Appendix A list: rank -> (slug, title). Pinned so drift is impossible.
TOPICS = {
    1: ("transmission-expansion-planning", "Transmission expansion planning"),
    2: ("grid-interconnection-queues", "Grid interconnection queues"),
    3: ("data-center-load-growth", "Data-center load growth"),
    4: ("capacity-expansion", "Capacity expansion"),
    5: ("resource-adequacy", "Resource adequacy"),
    6: ("system-flexibility-need", "System flexibility need"),
    7: ("cross-border-interconnection", "Cross-border interconnection"),
    8: ("renewable-integration", "Renewable integration"),
    9: ("net-zero-pathways", "Net-zero pathways"),
    10: ("battery-storage-sizing", "Battery storage sizing"),
    11: ("long-duration-storage-ldes", "Long-duration storage (LDES)"),
    12: ("curtailment-minimization", "Curtailment minimization"),
    13: ("demand-response", "Demand response"),
    14: ("dunkelflaute-low-vre-risk", "Dunkelflaute / low-VRE risk"),
    15: ("locational-electricity-markets", "Locational electricity markets"),
    16: ("grid-congestion-redispatch", "Grid congestion / redispatch"),
    17: ("capacity-market-design", "Capacity market design"),
    18: ("sector-coupling", "Sector coupling"),
    19: ("distribution-hosting-capacity", "Distribution hosting capacity"),
    20: ("smart-ev-charging", "Smart EV charging"),
    21: ("coal-early-retirement", "Coal early retirement"),
    22: ("universal-electricity-access", "Universal electricity access"),
    23: ("geospatial-electrification-mini-grid-vs-grid",
         "Geospatial electrification (mini-grid vs grid)"),
    24: ("green-hydrogen-siting", "Green hydrogen siting"),
    25: ("multi-year-weather-variability", "Multi-year weather variability"),
    26: ("peak-demand-forecasting", "Peak demand forecasting"),
    27: ("firm-low-carbon-capacity", "Firm low-carbon capacity"),
    28: ("solar-to-evening-peak-shift", "Solar-to-evening-peak shift"),
    29: ("vehicle-to-grid-v2g", "Vehicle-to-grid (V2G)"),
    30: ("heat-pump-grid-impact", "Heat pump grid impact"),
    31: ("balancing-market-valuation", "Balancing-market valuation"),
    32: ("ancillary-services-co-optimization", "Ancillary services co-optimization"),
    33: ("industrial-cluster-decarbonization", "Industrial cluster decarbonization"),
    34: ("electrolyser-grid-flexibility", "Electrolyser grid flexibility"),
    35: ("minimum-operational-demand", "Minimum operational demand"),
    36: ("rooftop-solar-saturation", "Rooftop solar saturation"),
    37: ("electricity-for-industrialization", "Electricity-for-industrialization"),
    38: ("climate-finance-eligibility-gco2-kwh",
         "Climate-finance eligibility (gCO2/kWh)"),
    39: ("discom-utility-financial-viability",
         "DISCOM / utility financial viability"),
    40: ("seasonal-storage-gap", "Seasonal storage gap"),
    41: ("green-ammonia-exports", "Green ammonia exports"),
    42: ("e-methanol-shipping-fuel", "E-methanol / shipping fuel"),
    43: ("steel-decarbonization-h2-dri", "Steel decarbonization (H2-DRI)"),
    44: ("cement-decarbonization", "Cement decarbonization"),
    45: ("high-temperature-industrial-heat", "High-temperature industrial heat"),
    46: ("district-heating-optimization", "District heating optimization"),
    47: ("thermal-storage", "Thermal storage"),
    48: ("building-retrofit-pathways", "Building retrofit pathways"),
    49: ("cooling-ac-peak-demand", "Cooling / AC peak demand"),
    50: ("hydropower-drought-risk", "Hydropower drought risk"),
    51: ("ultra-high-voltage-transmission", "Ultra-high-voltage transmission"),
    52: ("renewable-energy-zones", "Renewable energy zones"),
    53: ("offshore-wind-integration", "Offshore wind integration"),
    54: ("power-market-reform-spot-markets", "Power market reform / spot markets"),
    55: ("nuclear-smr-role", "Nuclear / SMR role"),
    56: ("ccs-ccu-deployment", "CCS / CCU deployment"),
    57: ("e-kerosene-aviation-fuel", "E-kerosene / aviation fuel"),
    58: ("blue-hydrogen-economics", "Blue hydrogen economics"),
    59: ("hydrogen-network-buildout", "Hydrogen network buildout"),
    60: ("energy-desalination-nexus", "Energy-desalination nexus"),
    61: ("aggregator-vpp-dispatch", "Aggregator / VPP dispatch"),
    62: ("load-shifting-industrial", "Load-shifting (industrial)"),
    63: ("asset-cost-benefit", "Asset cost-benefit"),
    64: ("extreme-weather-resilience", "Extreme-weather resilience"),
    65: ("security-of-supply-imports", "Security of supply / imports"),
    66: ("biomass-bioenergy-allocation", "Biomass / bioenergy allocation"),
    67: ("marginal-abatement-cost-curves", "Marginal abatement cost curves"),
    68: ("stranded-asset-risk", "Stranded-asset risk"),
    69: ("storage-revenue-stacking", "Storage revenue stacking"),
    70: ("fleet-ev-charging-siting", "Fleet EV charging siting"),
    71: ("regional-power-pool-modelling", "Regional power pool modelling"),
    72: ("grid-forming-inverters", "Grid-forming inverters"),
    73: ("system-inertia-stability", "System inertia / stability"),
    74: ("distributed-energy-resources-der", "Distributed energy resources (DER)"),
    75: ("prosumer-behind-the-meter", "Prosumer / behind-the-meter"),
    76: ("time-of-use-tariff-design", "Time-of-use tariff design"),
    77: ("green-h2-export-cost-benchmarking", "Green-H2 export cost benchmarking"),
    78: ("direct-electrification-vs-h2", "Direct electrification vs H2"),
    79: ("refinery-chemicals-feedstock", "Refinery / chemicals feedstock"),
    80: ("waste-heat-recovery", "Waste heat recovery"),
    81: ("demand-electrification-pathways", "Demand electrification pathways"),
    82: ("jetp-transition-financing", "JETP transition financing"),
    83: ("carbon-pricing-sensitivity", "Carbon pricing sensitivity"),
    84: ("uncertainty-near-optimal-mga", "Uncertainty / near-optimal spaces (MGA)"),
    85: ("robust-decision-making", "Robust decision-making"),
    86: ("open-input-data-assembly", "Open input-data assembly"),
    87: ("model-reproducibility", "Model reproducibility"),
    88: ("solver-speed-scalability", "Solver speed / scalability"),
    89: ("high-resolution-spatial-modelling", "High-resolution spatial modelling"),
    90: ("multi-sector-model-coupling", "Multi-sector model coupling"),
    91: ("ai-assisted-scenario-generation", "AI-assisted scenario generation"),
    92: ("non-expert-model-usability", "Non-expert model usability"),
    93: ("energy-affordability-equity", "Energy affordability / equity"),
    94: ("just-transition-impacts", "Just transition impacts"),
    95: ("critical-minerals-supply-chains", "Critical-minerals supply chains"),
    96: ("water-energy-land-nexus", "Water-energy-land nexus"),
    97: ("methane-gas-phase-down", "Methane / gas phase-down"),
    98: ("synthetic-natural-gas-e-sng", "Synthetic natural gas (e-SNG)"),
    99: ("geothermal-niche-baseload", "Geothermal / niche baseload"),
    100: ("tidal-wave-emerging", "Tidal / wave (emerging)"),
    # ranks > 100: zygon-native extensions beyond the Appendix A universe —
    # topics the interviews needed that the paper's ranking never carried.
    # Same contract, same checkers, both books required, v2-only expected.
    101: ("marginal-price-prediction", "Marginal price prediction"),
}


# ---------------------------------------------------------------- locations

def locate(qa_dir):
    """Resolve repo locations from a per-model _qa dir.

    zygon-native (2026-07-31): model roots resolve to <zygon>/models/<model>;
    override root with ZYGON_MODELS.
    """
    book_dir = os.path.dirname(qa_dir)
    cookbooks = os.path.dirname(book_dir)  # <zygon>/cookbooks/<model>
    _dir, _child = qa_dir, None
    while os.path.basename(_dir) != "cookbooks":
        if os.path.dirname(_dir) == _dir:
            sys.exit(f"cannot locate 'cookbooks' above {qa_dir}")
        _dir, _child = os.path.dirname(_dir), os.path.basename(_dir)
    zygon_root = os.path.dirname(_dir)
    cookbook_model = _child  # path segment after 'cookbooks'
    repo = os.path.join(
        os.environ.get("ZYGON_MODELS", os.path.join(zygon_root, "models")),
        cookbook_model)
    return {"book_dir": book_dir, "cookbooks": cookbooks, "zygon_root": zygon_root,
            "methods_dir": os.path.join(_dir, "methods"),
            "plots_dir": os.path.join(zygon_root, "plots"), "repo": repo}


def method_specs(methods_dir):
    """slug -> spec path. A method is <slug>.yaml, or <slug>/spec.yaml when it
    ships payload assets (same resolution as check_method_exec.py). v1 essays
    live in the v1/ subdir pending conversion."""
    specs = {os.path.basename(p)[:-5]: p
             for p in glob.glob(os.path.join(methods_dir, "*.yaml"))
             + glob.glob(os.path.join(methods_dir, "v1", "*.yaml"))}
    specs.update({os.path.basename(os.path.dirname(p)): p
                  for p in glob.glob(os.path.join(methods_dir, "*", "spec.yaml"))
                  if os.path.basename(os.path.dirname(p)) != "_qa"})
    specs.pop("TEMPLATE", None)
    return specs


# ---------------------------------------------------------------- registry

def check_registry(loc):
    """Validate FUNCTIONALITY.yaml. Returns (ids, errors)."""
    errors = []
    path = os.path.join(loc["book_dir"], "FUNCTIONALITY.yaml")
    reg = yaml.safe_load(open(path))
    if not isinstance(reg, list):
        return set(), ["FUNCTIONALITY.yaml top level must be a list"]
    ids = [d.get("id") for d in reg]
    if len(set(ids)) != len(ids):
        errors.append("duplicate functionality ids")
    for d in reg:
        label = f"functionality:{d.get('id', '<no-id>')}"
        for key in ("id", "title", "status", "surface", "note"):
            if key not in d:
                errors.append(f"{label}: missing field {key}")
        if d.get("status") not in STATUS_VOCAB:
            errors.append(f"{label}: bad status {d.get('status')!r}")
        consumer = d.get("consumer")
        if d.get("status") == "absent":
            if consumer:
                errors.append(f"{label}: absent capability must not name a consumer")
            continue
        if not consumer:
            errors.append(f"{label}: consumer required for status {d.get('status')!r}")
            continue
        if "http" in consumer or LINENO_RE.search(consumer):
            errors.append(f"{label}: URL or line number in consumer")
            continue
        for entry in consumer.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            fpath, _, symbol = entry.partition(":")
            full = os.path.join(loc["repo"], fpath.strip())
            if not os.path.isfile(full):
                errors.append(f"{label}: consumer file missing: {fpath}")
                continue
            content = open(full, errors="replace").read()
            if symbol.strip() not in content:
                errors.append(f"{label}: symbol {symbol.strip()!r} not found in {fpath}")
    return set(ids), errors


def recipe_slugs(loc, book):
    d = os.path.join(loc["cookbooks"], book)
    return {os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".yaml")}


# ------------------------------------------------------------------- cards

def method_status(spec_path, model):
    """(found_model_section, status) for a linked method spec, or (False, None)."""
    doc = yaml.safe_load(open(spec_path))
    for s in (doc.get("models") or []) if isinstance(doc, dict) else []:
        if s.get("model") == model:
            return True, s.get("status")
    return False, None


def check_card(path, stem, ctx):
    """Validate one card. Returns (errors, warnings, schema_version)."""
    card_errors, warnings = [], []

    def cerr(msg):
        card_errors.append(f"{stem}: {msg}")

    doc = yaml.safe_load(open(path))
    if not isinstance(doc, dict):
        return [f"{stem}: top level is not a mapping"], [], None

    sv = doc.get("schema_version")
    if sv is not None and sv != 2:
        return [f"{stem}: schema_version must be 2 or absent (v1)"], [], sv
    required = COMMON_KEYS + (V2_ONLY_KEYS if sv == 2 else V1_ONLY_KEYS)
    for key in required:
        if key not in doc:
            cerr(f"missing required key: {key}")
    if card_errors:
        return card_errors, warnings, sv

    if doc["id"] != stem or not SLUG_RE.match(str(doc["id"])):
        cerr(f"id {doc['id']!r} != stem or not kebab")
    rank = doc["rank"]
    if rank not in TOPICS:
        cerr(f"rank {rank!r} not in the pinned TOPICS universe")
    else:
        slug, title = TOPICS[rank]
        if slug != stem:
            cerr(f"rank {rank} belongs to slug {slug!r}")
        if doc["title"] != title:
            cerr(f"title {doc['title']!r} != canonical {title!r}")
    if not isinstance(doc["when_to_use"], list) or not doc["when_to_use"]:
        cerr("when_to_use must be a non-empty list")
    if doc["coverage"] not in COVERAGE_VOCAB:
        cerr(f"coverage {doc['coverage']!r} not in {sorted(COVERAGE_VOCAB)}")
    if not str(doc["gap_assessment"]).strip():
        cerr("gap_assessment empty")

    recipes = doc["recipes"] or {}
    for book, valid in (("generation_conversion", ctx["gc_slugs"]),
                        ("demand", ctx["demand_slugs"])):
        for slug in recipes.get(book) or []:
            if slug not in valid:
                cerr(f"recipes.{book} slug not found: {slug}")
    extra_books = set(recipes) - {"generation_conversion", "demand"}
    if extra_books:
        cerr(f"unknown recipes book(s): {sorted(extra_books)}")

    if sv == 2:
        card_errors.extend(_check_v2_links(doc, stem, ctx, warnings))
    else:
        funcs = doc["functionality"] or []
        if not isinstance(funcs, list) or not funcs:
            cerr("functionality must be a non-empty list")
        for f in funcs:
            if not isinstance(f, dict) or "id" not in f \
                    or not str(f.get("role", "")).strip():
                cerr(f"functionality entry needs id + role: {f!r}")
            elif f["id"] not in ctx["func_ids"]:
                cerr(f"functionality id not in registry: {f['id']}")

    models = doc["models"]
    if not isinstance(models, list) or len(models) != 1 \
            or models[0].get("model") != ctx["model"]:
        cerr(f"models must be a single {ctx['model']} entry")
    else:
        va = models[0].get("version_anchor", {})
        if not str(va.get("ref", "")).startswith(ctx["ref_prefix"]):
            cerr(f"version_anchor.ref does not start {ctx['ref_prefix']}")
        if "date" not in va:
            cerr("version_anchor.date missing")
    return card_errors, warnings, sv


def _check_v2_links(doc, stem, ctx, warnings):
    """methods: / defaults: — the v2 card's outbound edges into the methods book."""
    out = []

    def cerr(msg):
        out.append(f"{stem}: {msg}")

    if "functionality" in doc:
        cerr("functionality: not a v2 field — v2 cards link methods, "
             "not capability ids")

    methods = doc["methods"]
    if not isinstance(methods, list) or not methods:
        cerr("methods must be a non-empty list")
        methods = []
    seen = set()
    for k, m in enumerate(methods):
        if not isinstance(m, dict) or "id" not in m \
                or not str(m.get("role", "")).strip():
            cerr(f"methods[{k}] needs id + role: {m!r}")
            continue
        mid = m["id"]
        if not SLUG_RE.match(str(mid)):
            cerr(f"methods[{k}] id not kebab: {mid!r}")
            continue
        if mid in seen:
            cerr(f"methods[{k}] duplicate id: {mid}")
            continue
        seen.add(mid)
        spec_path = ctx["method_specs"].get(mid)
        if not spec_path:
            cerr(f"methods[{k}]: no method spec for {mid!r}")
            continue
        spec = yaml.safe_load(open(spec_path))
        if not isinstance(spec, dict) or spec.get("schema_version") != 2:
            cerr(f"methods[{k}]: {mid} is a v1 essay — v2 cards may only link "
                 "executable specs")
            continue
        found, status = method_status(spec_path, ctx["model"])
        if not found:
            cerr(f"methods[{k}]: {mid} has no {ctx['model']} section")
        elif status != "verified":
            warnings.append(
                f"{stem}: methods[{k}] {mid} is status {status} on "
                f"{ctx['model']} — linkable, not yet offerable")

    plots = doc.get("plots") or []
    if not isinstance(plots, list):
        cerr("plots must be a list")
        plots = []
    plot_ids = set()
    for k, pl in enumerate(plots):
        if not isinstance(pl, dict) or "id" not in pl \
                or not str(pl.get("role", "")).strip():
            cerr(f"plots[{k}] needs id + role: {pl!r}")
            continue
        pid = pl["id"]
        if not PLOT_ID_RE.match(str(pid)):
            cerr(f"plots[{k}] id not a card slug: {pid!r}")
            continue
        if pid in plot_ids:
            cerr(f"plots[{k}] duplicate id: {pid}")
            continue
        plot_ids.add(pid)
        if not os.path.isfile(os.path.join(ctx["plots_dir"], f"{pid}.py")):
            cerr(f"plots[{k}]: no plot card plots/{pid}.py")
            continue
        params = pl.get("params")
        if params is not None and not isinstance(params, dict):
            cerr(f"plots[{k}] params must be a mapping")

    defaults = doc.get("defaults") or []
    if not isinstance(defaults, list):
        cerr("defaults must be a list")
        defaults = []
    aspects = set()
    for k, d in enumerate(defaults):
        if not isinstance(d, dict) or not str(d.get("is", "")).strip():
            cerr(f"defaults[{k}] needs aspect + is: {d!r}")
            continue
        aspect = d.get("aspect")
        if not SLUG_RE.match(str(aspect)):
            cerr(f"defaults[{k}] aspect not kebab: {aspect!r}")
        elif aspect in aspects:
            cerr(f"defaults[{k}] duplicate aspect: {aspect}")
        elif aspect in seen:
            cerr(f"defaults[{k}] aspect {aspect!r} is also a linked method — "
                 "link the spec, do not declare it a default")
        aspects.add(aspect)
    return out


# -------------------------------------------------------------------- run

def run(qa_dir, expected_model, expected_ref_prefix, argv=None):
    """Entry point for the per-model drivers. Exits non-zero on failure."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry-only", action="store_true",
                    help="validate FUNCTIONALITY.yaml and exit (pre-card gate)")
    args = ap.parse_args(argv)

    loc = locate(qa_dir)
    func_ids, errors = check_registry(loc)
    if args.registry_only:
        _report(errors)
        print(f"functionality registry ok: {len(func_ids)} capabilities")
        return

    ctx = {"model": expected_model, "ref_prefix": expected_ref_prefix,
           "func_ids": func_ids,
           "gc_slugs": recipe_slugs(loc, "generation_conversion"),
           "demand_slugs": recipe_slugs(loc, "demand"),
           "method_specs": method_specs(loc["methods_dir"]),
           "plots_dir": loc["plots_dir"]}

    # v1 cards live in the v1/ subdir pending migration; a stem present in
    # both places is a stale leftover from a conversion and is an error.
    card_paths = {}
    for sub in ("v1", "."):
        d = os.path.join(loc["book_dir"], sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".yaml") or f == "FUNCTIONALITY.yaml":
                continue
            stem = os.path.splitext(f)[0]
            if stem in card_paths:
                errors.append(f"duplicate topic card: {stem}.yaml exists both "
                              "flat and under v1/")
            card_paths[stem] = os.path.join(d, f)
    on_disk = set(card_paths)
    canonical = {slug for slug, _ in TOPICS.values()}
    for missing in sorted(canonical - on_disk):
        errors.append(f"missing topic card: {missing}.yaml")
    for stray in sorted(on_disk - canonical):
        errors.append(f"stray yaml not in Appendix A: {stray}.yaml")

    n_ok, n_v2, warnings = 0, 0, []
    for stem in sorted(on_disk & canonical):
        card_errors, card_warnings, sv = check_card(
            card_paths[stem], stem, ctx)
        warnings.extend(card_warnings)
        in_v1 = os.path.basename(os.path.dirname(card_paths[stem])) == "v1"
        if sv == 2 and in_v1:
            card_errors.append(f"{stem}: v2 card filed under v1/ — move it up")
        elif sv != 2 and not in_v1:
            card_errors.append(f"{stem}: v1 card filed flat — move it to v1/")
        if card_errors:
            errors.extend(card_errors)
        else:
            n_ok += 1
        if sv == 2:
            n_v2 += 1

    _report(errors)
    for w in warnings:
        print(f"warn {w}")
    print(f"topics ok: {n_ok}/{len(TOPICS)} cards "
          f"({n_v2} v2, {len(TOPICS) - n_v2} v1 pending migration); "
          f"functionality registry: {len(func_ids)} capabilities")


def _report(errors):
    if errors:
        print(f"FAIL ({len(errors)} problems)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
