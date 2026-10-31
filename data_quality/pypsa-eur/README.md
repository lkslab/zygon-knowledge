# Data-quality cookbook (pypsa-eur) — per-country input-data assessment

Answers: *before running pypsa-eur for country X, which inputs are real data,
which silently degrade to proxies, and which silently disappear?* Scope: the
34 countries in `config/config.default.yaml` `countries:` (EU27 subset +
AL BA CH GB ME MK NO RS XK). Version anchor: `a6c45e5a` (upstream master, 2026-09-09;
the country cards were assessed at the previous anchor `849c8858` and re-anchored on
2026-09-10 — the dataset chain they describe is unchanged in substance, but the
consumer scripts moved: see `datasets.yaml` for the current `consumer:` paths).

## Grading

| grade | meaning |
|---|---|
| **A** | native country-specific data present (row / file / dir / polygon) |
| **B** | a global/continental dataset covers it, or the dataset is not applicable (e.g. EEZ for landlocked countries) |
| **C** | silent DEFAULT/proxy fallback (EU-average industry ratios, German traffic/heat profiles, hardcoded populations) |
| **D** | absent and the feature silently disappears (no gas grid, no TYNDP projects, zero CO2 storage) |

The headline gradient: EU27 core mostly A; **CH/NO/GB** carry native
substitutes (Swiss BFS, NESO/DESNZ) but miss the EU-scoped sources
(JRC-IDEES, Energy Atlas, Natura); the **Western Balkans** accumulate C/D
grades (EU-average industry, no hotmaps sites, population proxies); **XK** is
the worst-covered country in scope (no JRC-IDEES, no ARDECO NUTS3, hardcoded
World Bank GDP/pop, synthetic load hardcoded out, no gas grid, no TYNDP
projects).

## Contents

- `datasets.yaml` — AUTHORED registry of 32 input datasets: acquisition path
  (versioned `data/<name>/{archive,primary}/` layout), consuming `file:symbol`
  (grep-verified), per-country coverage, the exact fallback code path when a
  country is missing, and `used_by` backlinks into the generation_conversion
  and demand books.
- `countries/<ISO2>.yaml` — GENERATED scorecards (one per country): grade +
  detail per dataset, family rollups, powerplant fleet evidence.
- `MATRIX.csv` — GENERATED countries × datasets grade matrix.
- `INDEX.md` — GENERATED summary (grade distribution per dataset, best/worst
  covered countries).
- `maps/` — GENERATED per-dataset choropleths (`data_quality_maps.png` 32-panel
  grid; `data_quality_maps.html` folium with one toggleable layer per dataset).

## Regenerate / verify

`build_scorecards.py`, `plot_matrix_maps.py` and `check_registry.py` generated the scorecards from the archived `cookbooks/data_quality/_qa/` tree (git history before the 2026-10 trim), run in a pypsa-earth pixi environment.

Scorecards are deterministic (file probes + the `PROBE_OVERRIDES` dict of
code-read facts in `build_scorecards.py`, each justified by a file:symbol
comment) — never hand-edit them; fix the probe or the registry instead.
