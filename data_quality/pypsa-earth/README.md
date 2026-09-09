# Data-quality cookbook — per-country assessment (ex-Europe)

The other two cookbooks answer *"how do I model X and what data does it need"*;
this one answers *"what does country Y actually have"*. Scope: every `world_iso`
country **except Europe** (covered by a different PyPSA model). ~160 countries.

## Parts

- **`datasets.yaml`** — the authored registry: one entry per country-resolved
  data source pypsa-earth consumes (demand CAGRs, UNSD balances, salt caverns,
  OSM, GADM, WorldPop, cutouts, plant databases, the German traffic/BDEW proxies
  applied globally, …). Each entry carries a grounded `consumer` (`file:symbol`),
  the missing-country behavior, and `used_by` backlinks to the recipe slugs that
  depend on it — the recipes themselves stay untouched.
- **`countries/<ISO2>.yaml`** — GENERATED scorecards (never hand-edit): per
  dataset grade + detail, per-family rollup, and measured build evidence where a
  region containing the country has been built (grid fragmentation from
  `networks/<region>/base.nc`, fleet from `resources/<run>/powerplants.csv`).
- **`MATRIX.csv`** — countries × datasets grades at a glance.
- **`INDEX.md`** — generated summary (grade histograms, best/worst covered).
- **`maps/`** — GENERATED world maps of the matrix: `data_quality_maps.png`
  (all 22 datasets as a panel grid — the one-glance picture) and
  `data_quality_maps.html` (folium, one toggleable layer per dataset with
  per-country tooltips). Micro-states below Natural-Earth 110m resolution
  (26, mostly small islands) are in the matrix but not drawable.

## Grades

| grade | meaning |
|---|---|
| **A** | native country-specific data present (row / file / cached extract / measured build) |
| **B** | a global dataset covers it (global GADM, UNSD row, rasters, powerplantmatching) |
| **C** | **silent DEFAULT/proxy fallback** — the model runs but on borrowed numbers (DEFAULT CAGR rows, German traffic + BDEW profiles everywhere) |
| **D** | absent and the feature **silently disappears** (no cavern H2, no aluminium demand, no plant sites) |

C and D are the dangerous tiers: nothing crashes, results just quietly degrade.
Family rollup = worst grade among the family's datasets.

## How an agent uses this with the other cookbooks

1. Recipe (`generation_conversion/` or `demand/`) names a `data_dependency`.
2. `datasets.yaml` maps it to a dataset id (`used_by` backlinks) + the consumer
   code + what happens when data is missing.
3. `countries/<ISO2>.yaml` says what the target country actually has — check it
   BEFORE running a model whose result would silently degrade.

## Regenerate / verify

```bash
pixi run python cookbooks/data_quality/_qa/build_scorecards.py   # rebuild scorecards
pixi run python cookbooks/data_quality/_qa/check_registry.py     # QA registry + cards
pixi run python cookbooks/data_quality/_qa/plot_matrix_maps.py   # rebuild maps/
```

Scorecards improve automatically as more regions get built (new
`networks/<region>/base.nc` and `resources/<run>/powerplants.csv` are picked up
on the next run).
