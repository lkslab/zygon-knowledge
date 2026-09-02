# Demand cookbook — structural extensions to the recipe schema

The demand recipes follow the same contract as `generation_conversion/`
(`enderpearl/claude_instructions/recipes/RECIPE.schema.yaml` + `EXTRACTION.md`),
with three extensions. Rationale: demand kinds differ from supply technologies —
they exist in BOTH models with very different fidelity, and every demand kind is
characterized by the same four questions (what drives it, where does it go, what
shape does it have, how does it scale).

## 1. Two model sections per recipe

`models:` carries BOTH a `pypsa-earth` and a `pypsa-eur` entry (the schema is
already keyed topic→models[]; generation_conversion simply used one). Per section:

| model | version_anchor | repo root for provenance/lever resolution |
|---|---|---|
| pypsa-earth | `8435f4c8cc05f30088933b37b7db497ff860dc53`, 2026-07-08 | `/home/lukas/Desktop/earth/pypsa-earth` |
| pypsa-eur | `3e32e3c619f6ab79ada87759d6b915e9d5f3ff56`, 2026-06-16 | `/home/lukas/Desktop/enderpearl/pypsa-eur` |

Provenance file paths are repo-relative and resolve against the section's own
repo; lever keys resolve against that repo's default config
(`config.default.yaml` for earth, `config/config.default.yaml` for eur).
A model may be absent from a recipe only if the topic is meaningless for it
(rare; prefer an explicit "not covered" section).

## 2. `demand_dimensions` (optional per-model block)

Four one-liners answering the questions every demand kind poses:

```yaml
demand_dimensions:
  driver:   "what activity variable sets the level (e.g. tonnes of steel, population, GDP)"
  spatial:  "how it is allocated to nodes (e.g. hotmaps sites; GDP 0.6 + pop 0.4)"
  temporal: "what shapes the profile (e.g. degree-days + BDEW intraday; annual-constant)"
  scenario: "how it scales across years/scenarios (e.g. {demand}_{year} CAGRs; per-year config dicts)"
```

## 3. `reference_taxonomy` (optional top-level block)

Higher-fidelity framing from OUTSIDE the two repos — for this book, the
Fraunhofer ISI FORECAST industry model (process-level products, temperature-banded
process heat/cooling, cross-cutting technologies, efficiency-measure diffusion).
Shape:

```yaml
reference_taxonomy:
  framework: "FORECAST (Fraunhofer ISI)"
  concepts: [ "one line per higher-fidelity concept relevant to this topic", ... ]
  sources: [ "https://...", ... ]   # URLs live ONLY here
```

Hard rule preserved: the per-model `provenance` fields stay strictly repo-internal
`file:symbol` — external URLs never appear there. The QA checker validates all of
the above (`check_recipes.py` in this directory).

## Deliberate topic-scoping notes

- **data centers** and **desalination** demand are grounded absences in BOTH models;
  they are covered as boundary entries inside `electricity-load` and
  `space-cooling-demand` / the generation book's `desalination-flexible-load`
  rather than as separate demand recipes — a file whose every section says
  "absent, no anchor" would carry no retrieval value beyond that line.
- **cooking** is folded into residential energy totals in both models; the
  `cooking-energy-demand` recipe exists because the *ask* is common (clean-cooking
  transitions) and the recipe documents exactly where the fold happens.
