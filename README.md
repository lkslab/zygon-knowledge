# zygon-knowledge

The assistant's knowledge base for pypsa-app: YAML cards and CSV tables the app
reads at runtime through its `knowledge` package (`src/knowledge/` in the app).
The pin is the app's `src/pypsa_app/knowledge` gitlink; ship new content by
committing the new sha there. `CLAUDE.md` covers the link in detail.

## Layout

| path | what |
|---|---|
| `topics/<slug>.yaml` | one card per planning question |
| `carriers/<book>/<slug>.yaml` | one card per technology or demand segment; book is `generation_conversion` or `demand` |
| `methods/<slug>.yaml` or `methods/<slug>/spec.yaml` | method specs a topic cites; `payload/<model>/` beside a spec holds the files the method adds to a run |
| `data_quality/<model>/countries/<CC>.yaml` | generated per-country data-quality scorecards, next to `datasets.yaml`, `MATRIX.csv` and `INDEX.md` |
| `policy/*.csv` | the policy registry (`assets`, `targets`, `subsidies`, `regulation`, `coverage`, `blocs`, `technology_taxonomy`, `sources`) with its `tools/` and `_qa/` |
| `models/<model>` | gitlinks to pypsa-eur and pypsa-earth, the commits the cards cite |
| `tools/` | the validator, its checks and the citation resolver |

## Card shapes

A card is written once for every model it applies to: a top-level `models[]`
list with one section per model. The app's `src/knowledge/cards.py` defines the
shapes; unknown keys are ignored (`extra="ignore"`).

- `Topic`: `id, title, question, when_to_use[], models[]`. Section: `model, approach, trade_offs[], limitations[], methods[{id, role}], defaults[], plots[{id, role}], version_anchor{ref, date}`.
- `Carrier`: `id, book, title, summary, when_to_use[], models[]`. Section: `model, version_anchor, out_of_box, levers[{key, effect, default, provenance}], boundary[{variant, rung, note}], where[], data_dependencies[], demand_dimensions`. `rung` is `L0`..`L5`.
- `Method`: `id, title, family, what, when_to_use[], notes, models[]`. Section: `model, version_anchor, execution[], invalidates[], budget, success_metric[]`.
- `DataQuality`: `country, name, families, datasets, fleet_evidence, build_evidence, continent`.

`model` is `pypsa-eur` or `pypsa-earth`. A topic lists a model only when it has a section for it.

## How the app reads it

`Knowledge.open(root, model)` returns a handle per model; `Policy.open(root)`
returns the policy tables. Cards are re-read on every call, so an edit is visible
on the next call. The wheel and the image ship only the read set: topic,
carrier, method and `spec.yaml` cards, the data-quality country cards and
`policy/*.csv`. Everything else here stays out.

## Anchors

Every topic, carrier and method section cites a `version_anchor.ref`: pypsa-eur
`09e8910a`, the `lkslab/pypsa-eur` fork commit the app pins, and pypsa-earth
`8435f4c8`. Both equal the `models/<model>` gitlinks.

## Checks

```
python3 tools/validate.py --app <pypsa-app checkout>   # reader plus anchors, citation closure, payload layout
python3 -m pytest tools                                # the checks' own tests
python3 tools/resolve_eur_citations.py                 # every eur citation resolves in models/pypsa-eur
```

The validator needs pyyaml and pydantic and finds the app through `--app`,
`$PYPSA_APP` or the submodule layout. The resolver needs
`git submodule update --init models/pypsa-eur`. CI runs the first two
(`.github/workflows/validate.yaml`).

## History

The `archive`, `toymodels` and `basemaps` directories and `policy/_work` were removed in the 2026-10 trim; they live in git history.
