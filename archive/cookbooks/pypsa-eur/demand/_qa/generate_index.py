# -*- coding: utf-8 -*-
# PORTED from /home/lukas/Desktop/earth/pypsa-earth/cookbooks/demand/_qa/generate_index.py (2026-07-22).
# Changes: index preamble names the earth repo as the sibling (this copy lives in
#          the eur repo); logic and FAMILIES unchanged.
"""Generate cookbooks/demand/INDEX.md (dual-model coverage columns)."""

import os
import re

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPES_DIR = os.path.dirname(QA_DIR)

FAMILIES = {
    "Cross-sector machinery": [
        "electricity-load", "demand-scenarios-and-growth",
        "demand-spatial-disaggregation", "demand-temporal-profiles"],
    "Buildings": [
        "residential-space-heating-demand", "residential-water-heating-demand",
        "services-heat-demand", "residential-electricity-demand",
        "services-electricity-demand", "space-cooling-demand",
        "cooking-energy-demand", "building-heat-dsm"],
    "Transport": [
        "land-transport-demand", "rail-transport-demand", "aviation-demand",
        "shipping-demand", "agriculture-machinery-demand"],
    "Agriculture": ["agriculture-energy-demand"],
    "Industry — subsector families": [
        "steel-demand", "chemicals-demand", "cement-minerals-demand",
        "aluminium-nonferrous-demand", "pulp-paper-demand",
        "food-beverages-demand", "light-manufacturing-demand",
        "mining-construction-demand"],
    "Industry — cross-cutting (FORECAST-inspired)": [
        "industrial-process-heat-temperature-bands", "industrial-process-cooling",
        "industrial-crosscutting-electricity", "industrial-feedstocks-nonenergy",
        "industrial-process-emissions", "industrial-material-production-drivers",
        "industrial-efficiency-diffusion"],
    "Other demands": [
        "district-heating-demand-share", "hydrogen-export-demand",
        "electricity-distribution-losses"],
}


def verdict(model_section):
    if model_section is None:
        return "—"
    t = (model_section.get("out_of_box", {}).get("covers") or "").lower()
    if t.strip().startswith("not covered") or "not covered" in t[:120]:
        return "not covered"
    return "covered"


def entry_rung(model_section):
    if model_section is None:
        return "—"
    rungs = [b.get("rung") for b in (model_section.get("boundary") or []) if b.get("rung")]
    nums = sorted(int(r[1]) for r in rungs if re.match(r"^L[0-5]$", str(r)))
    if not nums:
        return "—"
    tag = " (proxy)" if verdict(model_section) == "not covered" else ""
    return f"L{nums[0]}{tag}"


def main():
    lines = [
        "# Demand cookbook — index",
        "",
        "One recipe per demand kind, covering BOTH pypsa-eur (anchor `849c8858`,",
        "2026-07-23, this repo) and pypsa-earth (anchor `8435f4c8`, 2026-07-08,",
        "repo `/home/lukas/Desktop/earth/pypsa-earth`), with FORECAST-inspired",
        "`reference_taxonomy` blocks on the industry cross-cutting topics.",
        "Structural extensions vs generation_conversion: `_qa/SCHEMA_NOTES.md`.",
        "*Entry rung* = lowest rung on that model's boundary ladder; `(proxy)` =",
        "cheapest crude approximation of an uncovered kind. Runtime validation",
        "(pypsa-earth side, executed from the earth repo): `VALIDATION.md`.",
        "",
    ]
    seen = set()
    for family, slugs in FAMILIES.items():
        lines += [
            f"## {family}", "",
            "| topic | slug | pypsa-earth | rung | pypsa-eur | rung |",
            "|---|---|---|---|---|---|",
        ]
        for slug in slugs:
            path = os.path.join(RECIPES_DIR, f"{slug}.yaml")
            if not os.path.isfile(path):
                lines.append(f"| *(missing)* | `{slug}` | — | — | — | — |")
                continue
            with open(path) as f:
                doc = yaml.safe_load(f)
            sections = {m.get("model"): m for m in doc["models"]}
            earth, eur = sections.get("pypsa-earth"), sections.get("pypsa-eur")
            lines.append(
                f"| {doc['title']} | [`{slug}`]({slug}.yaml) "
                f"| {verdict(earth)} | {entry_rung(earth)} "
                f"| {verdict(eur)} | {entry_rung(eur)} |"
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
