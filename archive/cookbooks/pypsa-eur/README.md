# Cookbooks — grounded modelling recipes (pypsa-eur)

Machine-retrievable "recipes" answering: *the user wants X — how does the model
cover X, which config keys tune it, where does config run out, and where do I make
the change?* Contract: `enderpearl/claude_instructions/recipes/`
(`EXTRACTION.md` = method, `RECIPE.schema.yaml` = shape). The golden rule: every
factual claim carries `file:symbol` provenance from a file the author actually
opened — mechanically enforced (symbols are grep-verified; line numbers rejected).

This is the pypsa-eur sibling of the suite at
`/home/lukas/Desktop/earth/pypsa-earth/cookbooks/` (same contract, same topic
universes, same QA tooling ported with marked changes). Version anchor for all
pypsa-eur content: commit `849c8858d2536ccf8eed0c2e838d22a474a7ee5d`
(2026-07-23, current HEAD).

**Dirty-tree caveat**: at the time of authoring, `scripts/build_renewable_profiles.py`
and `scripts/prepare_sector_network.py` carried uncommitted modifications on top
of the anchor. Provenance greps run against the working tree; recipe authors were
instructed to prefer symbols that exist in the committed version. If those files
are reverted/committed, re-run the checkers to catch stale symbols.

## Books

- **`generation_conversion/`** — supply/conversion/storage/grid/flexibility
  technology topics: the same 100-topic universe as the earth book (topics that
  pypsa-eur does not model, e.g. solar mini-grids, become honest "not covered"
  recipes with proxy rungs) plus a family of pypsa-eur-only topics the earth
  model lacks (methanol economy, CO2 transport & sequestration, Allam cycle,
  ATES, endogenous industry process heat, H2 pipeline retrofitting, distribution
  grid, TYNDP projects). Single model section per recipe (**pypsa-eur**).
- **`demand/`** — energy demand kinds; **verbatim copy of the shared dual-model
  book** (36 recipes, each with both a pypsa-earth and a pypsa-eur section; the
  eur sections are anchored at this repo's HEAD). The earth copy at
  `/home/lukas/Desktop/earth/pypsa-earth/cookbooks/demand/` is canonical for
  pypsa-earth content; sync from there rather than editing earth sections here.
  Runtime validation (earth Mexico prenetwork) lives earth-side only.
- **`topics/`** — 101 planning-question wiring cards (the 100 of Appendix A in
  `energy_topics/energy_modelling_demand_landscape.md`, ranked by urgency,
  plus zygon-native extensions at ranks > 100; the rank↔slug↔title universe is
  pinned in `cookbooks/_qa/topic_card_lib.py` and shared with the earth
  suite). Each card wires a topic to the recipes in the two books
  above AND to the model functionality it needs (`topics/FUNCTIONALITY.yaml` —
  capability registry with grep-verified consumers and honest
  working/partial/dead-key/absent status), with a pypsa-eur coverage verdict.
- **`data_quality/`** — per-country data-quality assessment for the countries in
  pypsa-eur's default scope (`config/config.default.yaml` `countries:` list):
  an authored dataset registry (`datasets.yaml`, with `used_by` backlinks into
  the other books) + script-GENERATED scorecards (`countries/<ISO2>.yaml`,
  `MATRIX.csv`) grading every country A–D per data source. A = native country
  data, B = global/continental dataset covers it, C = silent proxy/default
  fallback, D = data absent and the feature silently disappears. The headline
  gradient: EU27 core mostly A, CH/NO/GB mixed (native single-country sources vs
  no TYNDP), Western Balkans C (EU-average fallbacks, hardcoded populations),
  XK near D.

## Per-book tooling (`_qa/`)

- `check_*.py` — schema/provenance/config-key validators; run after any edit.
- `generate_index.py` — regenerates the book's `INDEX.md`.
- All ported scripts carry a `# PORTED from ...` header naming their earth
  source and the exact changes.

The scripts resolve all paths from their own location, so ANY python with
`pyyaml` + `pandas` can run them. Note: this repo's `pixi.toml` currently uses
`exclude-newer = "7d"`, which pixi 0.60 cannot parse, so `pixi run` from THIS
repo fails; use the earth repo's pixi env instead:

```bash
cd /home/lukas/Desktop/earth/pypsa-earth
pixi run python /home/lukas/Desktop/enderpearl/pypsa-eur/cookbooks/generation_conversion/_qa/check_recipes.py
pixi run python /home/lukas/Desktop/enderpearl/pypsa-eur/cookbooks/demand/_qa/check_recipes.py
pixi run python /home/lukas/Desktop/enderpearl/pypsa-eur/cookbooks/topics/_qa/check_topics.py
pixi run python /home/lukas/Desktop/enderpearl/pypsa-eur/cookbooks/data_quality/_qa/check_registry.py
```

Note the demand checker validates BOTH repos: eur provenance against this repo,
earth provenance against the hardcoded sibling path — moving either repo breaks
that direction.

## Reading order for an agent

0. If the user brings a *question* rather than a technology ("can we retire
   coal early?", "what does zonal pricing change?"), start from `topics/` —
   its card names the recipes and functionality to open next.
1. Scan the book's `INDEX.md` (`when_to_use` phrasing lives in each recipe).
2. Open the matching `<slug>.yaml`; the `boundary` ladder answers "from which point
   must I write code" (L0 config-flip … L5 bespoke Python; `(proxy)` = crude
   approximation of an uncovered tech).
3. Follow `provenance`/`where` anchors into this repo at (or near) the anchor
   commit; if a symbol no longer greps, the claim is stale.
4. Before trusting country-level results, check
   `data_quality/countries/<ISO2>.yaml` — C/D grades mean the run silently
   degrades (proxy fallbacks) or silently loses features for that country.

## Follow-ups not (yet) built

- An earth-carrier-coverage analog of the earth suite's
  `cookbooks/_qa/eur_carrier_coverage.py` (mapping pypsa-earth carrier names
  onto these recipes).
- A pypsa-eur runtime-validation analog of the earth `VALIDATION.md`
  (recipe→component assertions against solved eur networks).
