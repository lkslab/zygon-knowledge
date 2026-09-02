# -*- coding: utf-8 -*-
# PORTED from /home/lukas/Desktop/earth/pypsa-earth/cookbooks/generation_conversion/_qa/generate_index.py (2026-07-22).
# Changes: header text (pypsa-eur, anchor 849c8858, no Mexico-validation line);
#          FAMILIES: "parity sweep" family renamed plain "Conventional & fossil";
#          new family "pypsa-eur additions" (10 topics the earth model lacks).
"""Generate recipes/INDEX.md from the recipe files (run after any recipe change)."""

import os
import re

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPES_DIR = os.path.dirname(QA_DIR)

FAMILIES = {
    "Supply — variable renewables": [
        "utility-scale-solar-pv", "onshore-wind", "offshore-wind",
        "rooftop-distributed-solar", "concentrated-solar-power",
        "floating-offshore-wind", "floating-solar", "conventional-hydropower"],
    "Supply — firm / emerging": [
        "run-of-river-hydro", "small-modular-reactors", "conventional-nuclear",
        "enhanced-geothermal", "geothermal-conventional", "nuclear-fusion"],
    "Conventional & fossil": [
        "gas-power-plants", "coal-power-plants", "oil-power-plants",
        "combined-heat-and-power", "waste-to-energy", "fossil-fuel-boilers",
        "fossil-fuel-supply", "natural-gas-pipelines", "green-energy-imports"],
    "Grid & interconnection": [
        "hv-transmission-lines", "hvdc-interconnectors", "uhv-dc",
        "grid-forming-inverters", "synchronous-condensers",
        "dynamic-line-rating-facts", "solar-mini-grids", "solar-home-systems",
        "smart-meters"],
    "Storage": [
        "grid-scale-batteries", "long-duration-storage", "pumped-hydro-storage",
        "thermal-storage", "flow-batteries", "sodium-ion-batteries",
        "iron-air-batteries", "compressed-air-storage", "liquid-air-storage",
        "gravity-storage", "hydrogen-storage-salt-caverns"],
    "Transport": [
        "battery-electric-cars", "electric-heavy-trucks", "smart-ev-chargers",
        "vehicle-to-grid", "electric-buses", "rail-electrification",
        "catenary-trucks", "hydrogen-fuel-cell-trucks", "electric-ferries",
        "ammonia-ships", "methanol-ships", "hydrogen-aircraft"],
    "Buildings & low-temperature heat": [
        "air-source-heat-pumps", "ground-source-heat-pumps",
        "heat-pump-water-heaters", "building-retrofit", "district-heating",
        "solar-thermal", "electric-cooking", "clean-cookstoves",
        "electric-resistance-heating"],
    "Hydrogen & low-carbon fuels": [
        "electrolysers", "green-hydrogen", "green-ammonia", "blue-hydrogen",
        "hydrogen-pipelines", "e-methanol", "e-kerosene-saf",
        "e-diesel-fischer-tropsch", "e-sng", "stationary-fuel-cells",
        "advanced-biofuels"],
    "Industry (hard-to-abate)": [
        "electric-arc-furnace", "h2-dri-steel", "industrial-heat-pumps",
        "electric-boilers", "electric-process-heat", "low-clinker-cement",
        "inert-anode-aluminium", "electrolytic-chemicals",
        "mechanical-vapour-recompression", "waste-heat-recovery",
        "industrial-ccs"],
    "Bioenergy, waste & agriculture": [
        "biomass-bioenergy", "biogas-anaerobic-digestion", "landfill-gas",
        "electric-farm-machinery"],
    "Carbon removal (CDR)": [
        "direct-air-capture", "beccs", "biochar", "enhanced-rock-weathering",
        "ocean-cdr"],
    "Flexibility & cross-cutting": [
        "virtual-power-plants", "behind-the-meter-der",
        "desalination-flexible-load", "methane-abatement", "tidal-wave"],
    "pypsa-eur additions (no earth counterpart)": [
        "biomass-to-methanol", "methanol-reforming", "methanol-to-power",
        "co2-transport-and-sequestration", "allam-cycle",
        "aquifer-thermal-storage", "hydrogen-pipeline-retrofitting",
        "industry-process-heat-endogenous", "electricity-distribution-grid",
        "transmission-expansion-projects"],
}


def coverage_verdict(covers_text):
    """One-word-ish verdict from the out_of_box.covers prose."""
    t = (covers_text or "").lower()
    if t.strip().startswith("not covered") or "not covered" in t[:120]:
        return "not covered"
    return "covered"


def entry_rung(model, verdict):
    rungs = [b.get("rung") for b in (model.get("boundary") or []) if b.get("rung")]
    nums = sorted(int(r[1]) for r in rungs if re.match(r"^L[0-5]$", str(r)))
    if not nums:
        return "—"
    # For a not-covered topic, the lowest rung is by definition a workaround/
    # approximation (the tech has no first-class representation) — label it so
    # "not covered" + L0/L1 reads as "cheap proxy exists", not a contradiction.
    return f"L{nums[0]} (proxy)" if verdict == "not covered" else f"L{nums[0]}"


def one_liner(text, limit=110):
    line = " ".join((text or "").split())
    return line[: limit - 1] + "…" if len(line) > limit else line


def main():
    lines = [
        "# PyPSA-Eur recipe book — index",
        "",
        "One modelling recipe per technology topic, extracted per the contract in",
        "`enderpearl/claude_instructions/recipes/` (EXTRACTION.md + RECIPE.schema.yaml).",
        "Every claim carries `file:symbol` provenance; version anchor: commit",
        "`849c8858` (2026-07-23). *Entry rung* = the lowest rung on the recipe's",
        "boundary ladder (L0 = flip a config key … L5 = bespoke Python). For",
        "\"not covered\" topics the entry rung is marked *(proxy)*: the model has",
        "no first-class representation of the tech, but its cheapest crude",
        "approximation needs only that rung; the recipe's boundary ladder gives",
        "the proper implementation rung. The topic universe mirrors the",
        "pypsa-earth book (same 100 slugs) plus a pypsa-eur-only family.",
        "",
    ]
    seen = set()
    for family, slugs in FAMILIES.items():
        lines += [f"## {family}", "", "| topic | slug | coverage | entry rung |", "|---|---|---|---|"]
        for slug in slugs:
            path = os.path.join(RECIPES_DIR, f"{slug}.yaml")
            if not os.path.isfile(path):
                lines.append(f"| *(missing)* | `{slug}` | — | — |")
                continue
            with open(path) as f:
                doc = yaml.safe_load(f)
            model = doc["models"][0]
            verdict = coverage_verdict(model.get("out_of_box", {}).get("covers", ""))
            lines.append(
                f"| {doc['title']} | [`{slug}`]({slug}.yaml) | {verdict} | {entry_rung(model, verdict)} |"
            )
            seen.add(slug)
        lines.append("")

    extra = sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(RECIPES_DIR)
        if f.endswith(".yaml") and os.path.splitext(f)[0] not in seen
    )
    if extra:
        lines += ["## Unindexed", ""] + [f"- `{s}`" for s in extra] + [""]

    out = os.path.join(RECIPES_DIR, "INDEX.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {out}: {len(seen)} indexed, {len(extra)} unindexed")


if __name__ == "__main__":
    main()
