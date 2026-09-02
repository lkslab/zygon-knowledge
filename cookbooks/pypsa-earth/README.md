# Cookbooks — grounded modelling recipes

Machine-retrievable "recipes" answering: *the user wants X — how does the model
cover X, which config keys tune it, where does config run out, and where do I make
the change?* Contract: `enderpearl/claude_instructions/recipes/`
(`EXTRACTION.md` = method, `RECIPE.schema.yaml` = shape). The golden rule: every
factual claim carries `file:symbol` provenance from a file the author actually
opened — mechanically enforced (symbols are grep-verified; line numbers rejected).

## Books

- **`generation_conversion/`** — 100 supply/conversion/storage/grid/flexibility
  technology topics (the original 91 + a conventional/fossil parity sweep against
  pypsa-eur: gas/coal/oil power plants, CHP, waste-to-energy, fossil boilers,
  fossil supply chains, gas pipelines, green imports). Single model section per
  recipe (**pypsa-earth**, anchor `8435f4c8`, 2026-07-08). Runtime-validated
  against coarse solved Mexico networks (see its `VALIDATION.md`; 46/46
  recipe→component assertions).
- **`demand/`** — energy demand kinds: the union of what **pypsa-earth** (anchor
  `8435f4c8`) and **pypsa-eur** (anchor `3e32e3c6`, 2026-06-16, repo
  `/home/lukas/Desktop/enderpearl/pypsa-eur`) represent, plus higher-fidelity
  industry demand framing from the Fraunhofer ISI FORECAST model. Recipes carry
  **two model sections** and three structural extensions documented in
  `demand/_qa/SCHEMA_NOTES.md` (`demand_dimensions`, `reference_taxonomy`,
  dual anchors). pypsa-earth sections runtime-validated against the existing
  Mexico sector prenetwork; pypsa-eur sections grounded by provenance QA.
- **`topics/`** — 101 planning-question wiring cards (the 100 of Appendix A in
  `energy_topics/energy_modelling_demand_landscape.md`, ranked by urgency,
  plus zygon-native extensions at ranks > 100).
  Each card wires a topic ("transmission expansion planning", "coal early
  retirement") to the relevant recipes in the two books above AND to the model
  functionality it needs (`topics/FUNCTIONALITY.yaml` — 68 capabilities with
  grep-verified consumers and honest working/partial/dead-key/absent status),
  with a coverage verdict (35 ready / 38 partial / 27 gap).
- **`data_quality/`** — per-country data-quality assessment for the 160
  non-European countries: an authored dataset registry (`datasets.yaml`, with
  `used_by` backlinks into the other two books) + script-GENERATED scorecards
  (`countries/<ISO2>.yaml`, `MATRIX.csv`) grading every country A–D per data
  source, enriched with measured build evidence (grid fragmentation, fleet)
  from already-built networks. See its `README.md` for the grading legend.

## pypsa-eur vocabulary

Every `tech_colors` carrier of pypsa-eur (`config/plotting.default.yaml`, 341
keys) is mapped onto these recipes: `PYPSA_EUR_COVERAGE.md` (generated) holds
the full key→recipe table, and each mapped recipe carries its eur names as a
`when_to_use` line `"known in pypsa-eur as: ..."`. Regenerate/verify with
`pixi run python cookbooks/_qa/eur_carrier_coverage.py` (fails loudly when
pypsa-eur adds carriers that no recipe covers).

## Per-book tooling (`_qa/`)

- `check_recipes.py` — schema/provenance/config-key validator; run after any edit.
- `generate_index.py` — regenerates `INDEX.md` from the recipe files.
- assertion scripts — map recipe claims to observable components in built networks.

## Reading order for an agent

0. If the user brings a *question* rather than a technology ("can we retire
   coal early?", "what does zonal pricing change?"), start from `topics/` —
   its card names the recipes and functionality to open next.
1. Scan the book's `INDEX.md` (`when_to_use` phrasing lives in each recipe).
2. Open the matching `<slug>.yaml`; the `boundary` ladder answers "from which point
   must I write code" (L0 config-flip … L5 bespoke Python; `(proxy)` = crude
   approximation of an uncovered tech).
3. Follow `provenance`/`where` anchors into the repo at (or near) the recipe's
   `version_anchor` commit; if a symbol no longer greps, the claim is stale.
4. Before running a model for a specific country, check
   `data_quality/countries/<ISO2>.yaml` — C/D grades mean the run would silently
   degrade (DEFAULT/proxy fallbacks) or silently lose features.
