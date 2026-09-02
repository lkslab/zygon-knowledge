# -*- coding: utf-8 -*-
"""
Map every pypsa-eur plotting carrier (config/plotting.default.yaml tech_colors)
onto the cookbook recipes, so eur-side vocabulary retrieves the right recipe.

Does three things:
  1. asserts the explicit MAPPING below accounts for EVERY tech_colors key
     (fails loudly when pypsa-eur adds new carriers);
  2. inserts/updates one `when_to_use` line per mapped recipe:
       - "known in pypsa-eur as: <carrier>, <carrier>, ..."
     (idempotent: an existing 'known in pypsa-eur as' line is replaced);
  3. writes cookbooks/PYPSA_EUR_COVERAGE.md — the full key -> recipe table.

MAPPING is target-recipe -> [tech_colors keys]. SKIP holds pure bookkeeping
carriers (emission accounting, aggregation buckets) that are deliberately not
mapped to any recipe.

Usage: pixi run python cookbooks/_qa/eur_carrier_coverage.py
"""

import os
import sys

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
COOKBOOKS = os.path.dirname(QA_DIR)
PLOTTING = "/home/lukas/Desktop/enderpearl/pypsa-eur/config/plotting.default.yaml"
BOOKS = ("generation_conversion", "demand")
ALIAS_PREFIX = "known in pypsa-eur as: "

MAPPING = {
    # --- wind / solar / hydro ---
    "onshore-wind": ["onwind", "onshore wind"],
    "offshore-wind": ["offwind", "offshore wind", "offwind-ac", "offshore wind (AC)",
                      "offshore wind ac", "offwind-dc", "offshore wind (DC)",
                      "offshore wind dc"],
    "floating-offshore-wind": ["offwind-float", "offshore wind (Float)",
                               "offshore wind float"],
    "conventional-hydropower": ["hydro", "hydro reservoir", "hydroelectricity"],
    "run-of-river-hydro": ["ror", "run of river"],
    "pumped-hydro-storage": ["PHS", "hydro+PHS"],
    "utility-scale-solar-pv": ["solar", "solar PV", "solar-hsat"],
    "solar-thermal": ["solar thermal", "residential rural solar thermal",
                      "services rural solar thermal",
                      "residential urban decentral solar thermal",
                      "services urban decentral solar thermal",
                      "urban central solar thermal"],
    "rooftop-distributed-solar": ["solar rooftop"],
    # --- thermal power (new recipes) ---
    "gas-power-plants": ["OCGT", "OCGT marginal", "OCGT-heat", "CCGT",
                         "CCGT marginal", "allam", "gas-to-power/heat"],
    "coal-power-plants": ["Coal", "coal", "Coal marginal", "Lignite", "lignite",
                          "Lignite marginal"],
    "oil-power-plants": ["oil"],
    "conventional-nuclear": ["Nuclear", "Nuclear marginal", "nuclear", "uranium"],
    "combined-heat-and-power": ["CHP", "CHP CC", "CHP heat", "CHP electric",
                                "urban central gas CHP", "urban central gas CHP CC",
                                "urban central solid biomass CHP",
                                "urban central solid biomass CHP CC"],
    "waste-to-energy": ["municipal solid waste", "waste", "waste CHP",
                        "waste CHP CC"],
    # --- fossil supply chains / boilers (new recipes) ---
    "fossil-fuel-supply": ["gas", "fossil gas", "natural gas", "methane",
                           "oil primary", "oil refining", "imported oil"],
    "fossil-fuel-boilers": ["gas boiler", "gas boilers", "gas boiler marginal",
                            "residential rural gas boiler",
                            "residential urban decentral gas boiler",
                            "services rural gas boiler",
                            "services urban decentral gas boiler",
                            "urban central gas boiler", "oil boiler",
                            "residential rural oil boiler",
                            "services rural oil boiler",
                            "residential urban decentral oil boiler",
                            "urban central oil boiler",
                            "services urban decentral oil boiler",
                            "retrofitted H2 boiler"],
    "natural-gas-pipelines": ["gas pipeline", "gas pipeline new"],
    "green-energy-imports": ["import H2", "import gas", "import NH3", "import oil",
                             "import methanol"],
    # --- biomass / biofuels ---
    "biogas-anaerobic-digestion": ["biogas", "biogas to gas", "biogas to gas CC"],
    "biomass-bioenergy": ["biomass", "solid biomass", "solid biomass import",
                          "solid biomass transport", "unsustainable solid biomass",
                          "solid biomass to hydrogen", "biomass boiler",
                          "residential rural biomass boiler",
                          "residential urban decentral biomass boiler",
                          "services rural biomass boiler",
                          "services urban decentral biomass boiler"],
    "advanced-biofuels": ["biomass to liquid", "unsustainable bioliquids",
                          "electrobiofuels"],
    "e-sng": ["BioSNG", "BioSNG CC", "Sabatier", "methanation", "power-to-gas"],
    # --- grid ---
    "hv-transmission-lines": ["lines", "transmission lines", "AC", "AC-AC",
                              "AC line"],
    "hvdc-interconnectors": ["links", "HVDC links", "DC", "DC-DC", "DC link"],
    "electricity-distribution-losses": ["electricity distribution grid",
                                        "low voltage"],
    # --- storage ---
    "grid-scale-batteries": ["battery", "battery storage", "battery charger",
                             "battery discharger", "li-ion", "li-ion charger",
                             "li-ion discharger", "lfp", "lfp charger",
                             "lfp discharger"],
    "behind-the-meter-der": ["home battery", "home battery storage",
                             "home battery charger", "home battery discharger"],
    "flow-batteries": ["vanadium", "vanadium charger", "vanadium discharger"],
    "liquid-air-storage": ["lair", "lair charger", "lair discharger"],
    "compressed-air-storage": ["pair", "pair charger", "pair discharger"],
    "iron-air-batteries": ["iron-air", "iron-air charger", "iron-air discharger"],
    "thermal-storage": ["water tanks", "residential rural water tanks",
                        "services rural water tanks",
                        "residential urban decentral water tanks",
                        "services urban decentral water tanks",
                        "urban central water tanks", "hot water storage",
                        "hot water charging", "hot water discharging",
                        "urban central water tanks charger",
                        "urban central water tanks discharger",
                        "residential rural water tanks charger",
                        "residential rural water tanks discharger",
                        "residential urban decentral water tanks charger",
                        "residential urban decentral water tanks discharger",
                        "services rural water tanks charger",
                        "services rural water tanks discharger",
                        "services urban decentral water tanks charger",
                        "services urban decentral water tanks discharger",
                        "water pits", "water pits charger", "water pits discharger",
                        "urban central water pits",
                        "urban central water pits charger",
                        "urban central water pits discharger",
                        "aquifer thermal energy storage",
                        "aquifer thermal energy storage charger",
                        "aquifer thermal energy storage discharger"],
    # --- EVs ---
    "battery-electric-cars": ["land transport EV", "EV battery"],
    "smart-ev-chargers": ["BEV charger"],
    "vehicle-to-grid": ["V2G"],
    # --- heating supply ---
    "air-source-heat-pumps": ["heat pumps", "heat pump", "air heat pump",
                              "residential rural air heat pump",
                              "residential urban decentral air heat pump",
                              "services rural air heat pump",
                              "services urban decentral air heat pump",
                              "urban central air heat pump", "Ambient",
                              "power-to-heat"],
    "ground-source-heat-pumps": ["ground heat pump", "geothermal heat pump",
                                 "urban central geothermal heat pump",
                                 "residential rural ground heat pump",
                                 "services rural ground heat pump"],
    "electric-resistance-heating": ["resistive heater",
                                    "residential rural resistive heater",
                                    "residential urban decentral resistive heater",
                                    "services rural resistive heater",
                                    "services urban decentral resistive heater",
                                    "urban central resistive heater"],
    "district-heating": ["district heating", "ptes heat pump",
                         "urban central ptes heat pump", "river_water heat",
                         "river_water heat pump", "sea_water heat",
                         "sea_water heat pump"],
    "geothermal-conventional": ["geothermal", "geothermal heat",
                                "geothermal district heat",
                                "geothermal heat direct utilisation",
                                "geothermal organic rankine cycle"],
    "building-retrofit": ["retrofitting", "building retrofitting"],
    "electric-boilers": ["heat100-200 industry electric boiler steam"],
    "industrial-heat-pumps": [
        "heat100-200 industry industrial heat pump high temperature"],
    # --- hydrogen / derived fuels ---
    "green-hydrogen": ["H2", "hydrogen"],
    "blue-hydrogen": ["SMR", "SMR CC"],
    "electrolysers": ["H2 Electrolysis", "H2 electrolysis", "power-to-H2"],
    "stationary-fuel-cells": ["H2 Fuel Cell", "H2 fuel cell", "H2 turbine"],
    "hydrogen-pipelines": ["H2 pipeline", "H2 pipeline retrofitted"],
    "hydrogen-storage-salt-caverns": ["hydrogen storage", "H2 Store", "H2 storage"],
    "hydrogen-fuel-cell-trucks": ["land transport fuel cell"],
    "green-ammonia": ["NH3", "ammonia", "ammonia store", "ammonia cracker",
                      "Haber-Bosch"],
    "e-diesel-fischer-tropsch": ["Fischer-Tropsch", "liquid", "power-to-liquid"],
    "e-kerosene-saf": ["methanol-to-kerosene"],
    "e-methanol": ["methanol", "methanol transport", "methanolisation",
                   "biomass-to-methanol", "biomass-to-methanol CC",
                   "Methanol steam reforming", "Methanol steam reforming CC",
                   "methanol-to-olefins/aromatics", "allam methanol",
                   "CCGT methanol", "CCGT methanol CC", "OCGT methanol"],
    "methanol-ships": ["shipping methanol"],
    # --- CO2 management ---
    "industrial-ccs": ["CC", "CCS", "CO2 sequestration", "co2", "co2 stored",
                       "co2 sequestered", "co2 vent", "CO2 pipeline",
                       "gas for industry CC", "gas for industry co2 to atmosphere",
                       "gas for industry co2 to stored",
                       "solid biomass for industry CC",
                       "solid biomass for industry co2 from atmosphere",
                       "solid biomass for industry co2 to stored"],
    "direct-air-capture": ["DAC"],
    # --- demand book ---
    "electricity-load": ["Electric load", "electric demand", "electricity"],
    "industrial-crosscutting-electricity": ["industry electricity",
                                            "industry new electricity"],
    "industrial-process-heat-temperature-bands": [
        "gas for industry", "coal for industry", "solid biomass for industry",
        "low-temperature heat for industry", "process heat",
        "heat100-200 industry", "heat200-500 industry", "heat>500 industry",
        "heat100-200 industry gas", "heat200-500 industry gas",
        "heat>500 industry gas", "heat100-200 industry gas CC",
        "heat200-500 industry gas CC", "heat>500 industry gas CC",
        "heat100-200 industry solid biomass", "heat200-500 industry solid biomass",
        "heat100-200 industry solid biomass CC",
        "heat200-500 industry solid biomass CC",
        "heat100-200 industry hydrogen", "heat200-500 industry hydrogen",
        "heat>500 industry hydrogen"],
    "industrial-feedstocks-nonenergy": ["H2 for industry", "naphtha for industry"],
    "industrial-process-emissions": ["process emissions", "process emissions CC",
                                     "process emissions to stored",
                                     "process emissions to atmosphere"],
    "chemicals-demand": ["industry methanol", "non-sequestered HVC", "HVC to air"],
    "residential-space-heating-demand": ["Heat load", "heat", "heat demand",
                                         "rural heat", "residential rural heat",
                                         "decentral heat",
                                         "residential urban decentral heat"],
    "services-heat-demand": ["services rural heat",
                             "services urban decentral heat"],
    "district-heating-demand-share": ["central heat", "urban central heat"],
    "building-heat-dsm": ["rural heat dsm", "urban central heat dsm",
                          "residential urban decentral heat dsm"],
    "land-transport-demand": ["land transport oil", "land transport demand"],
    "shipping-demand": ["shipping", "shipping oil", "H2 for shipping"],
    "aviation-demand": ["kerosene for aviation"],
    "agriculture-energy-demand": ["agriculture electricity", "agriculture heat"],
    "agriculture-machinery-demand": ["agriculture machinery oil"],
    "electric-farm-machinery": ["agriculture machinery electric"],
    "hydrogen-export-demand": ["H2 liquefaction"],
}

# pure bookkeeping carriers: emission accounting flows and aggregation buckets
SKIP = {
    "solid", "heat vent", "urban central heat vent", "other", "load",
    "oil emissions", "shipping oil emissions", "shipping methanol emissions",
    "land transport oil emissions", "agriculture machinery oil emissions",
}


def recipe_path(slug):
    for book in BOOKS:
        path = os.path.join(COOKBOOKS, book, f"{slug}.yaml")
        if os.path.isfile(path):
            return path
    return None


def annotate(path, carriers):
    """Insert/replace the alias line as the last when_to_use item."""
    with open(path) as f:
        lines = f.readlines()
    alias_line = f'  - "{ALIAS_PREFIX}{", ".join(carriers)}"\n'
    lines = [l for l in lines if ALIAS_PREFIX not in l]
    start = next(i for i, l in enumerate(lines) if l.startswith("when_to_use:"))
    end = start + 1
    while end < len(lines) and (lines[end].startswith("  - ")
                                or lines[end].startswith("    ")):
        end += 1
    lines.insert(end, alias_line)
    with open(path, "w") as f:
        f.writelines(lines)


def main():
    keys = list(yaml.safe_load(open(PLOTTING))["plotting"]["tech_colors"])
    reverse = {}
    for slug, carriers in MAPPING.items():
        for c in carriers:
            if c in reverse:
                print(f"FATAL: {c!r} mapped to both {reverse[c]} and {slug}")
                sys.exit(1)
            reverse[c] = slug

    unmapped = [k for k in keys if k not in reverse and k not in SKIP]
    stale = sorted((set(reverse) | SKIP) - set(keys))
    if unmapped:
        print(f"FAIL: {len(unmapped)} tech_colors keys unmapped:")
        for k in unmapped:
            print(f"  - {k}")
        sys.exit(1)
    if stale:
        print(f"note: {len(stale)} mapped keys no longer in plotting.yaml: {stale}")

    n_annotated, missing_recipes = 0, []
    for slug, carriers in sorted(MAPPING.items()):
        path = recipe_path(slug)
        if path is None:
            missing_recipes.append(slug)
            continue
        annotate(path, carriers)
        n_annotated += 1

    with open(os.path.join(COOKBOOKS, "PYPSA_EUR_COVERAGE.md"), "w") as f:
        f.write(
            "# pypsa-eur carrier coverage\n\n"
            "GENERATED by `_qa/eur_carrier_coverage.py` — do not hand-edit.\n\n"
            "Every `tech_colors` key of pypsa-eur `config/plotting.default.yaml`"
            f" ({len(keys)} keys), mapped to the cookbook recipe that covers the"
            " concept (many keys are color-aliases of one concept). Mapped"
            " recipes carry the same list in their `when_to_use` (line"
            f" '{ALIAS_PREFIX}...'). 'bookkeeping' = emission-accounting or"
            " aggregation carriers with no technology/demand behind them.\n\n"
            "| pypsa-eur tech_colors key | recipe (book) |\n|---|---|\n")
        for k in keys:
            if k in SKIP:
                f.write(f"| {k} | *bookkeeping — deliberately unmapped* |\n")
            else:
                slug = reverse[k]
                path = recipe_path(slug)
                book = os.path.basename(os.path.dirname(path)) if path else "MISSING"
                f.write(f"| {k} | [{slug}]({book}/{slug}.yaml) ({book}) |\n")

    print(f"tech_colors keys: {len(keys)}; mapped: {len(reverse)} onto "
          f"{len(MAPPING)} recipes; bookkeeping-skipped: {len(SKIP)}")
    print(f"annotated {n_annotated} recipes; wrote PYPSA_EUR_COVERAGE.md")
    if missing_recipes:
        print(f"RECIPES STILL MISSING ({len(missing_recipes)}): "
              f"{' '.join(missing_recipes)}")
        sys.exit(2)


if __name__ == "__main__":
    main()
