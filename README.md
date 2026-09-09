# zygon-knowledge

The assistant's knowledge base for pypsa-app. The app pins one commit of this
repo (`KNOWLEDGE_REV` in its `src/agent/knowledge.py`) and reads the cards
below at runtime; bump the pin to ship new content.

## Layout

| path | what | shape |
|---|---|---|
| `topics/<slug>.yaml` | one card per planning question, seven of them | `id, title, question, when_to_use[], models[]` where each `models[]` entry is `{model, coverage, gap_assessment, recipes{generation_conversion[], demand[]}, methods[{id, role}], defaults[], plots[], version_anchor{ref, date}}` |
| `recipes/generation_conversion/<slug>.yaml`, `recipes/demand/<slug>.yaml` | technology and demand recipes, shared across models | `id, title, summary, when_to_use[], models[]` where each entry is `{model, version_anchor, out_of_box, levers[], boundary[{variant, rung, note}], where[], data_dependencies[]}` |
| `methods/<slug>.yaml` or `methods/<slug>/spec.yaml` + `payload/<model>/` | executable method specs, only the ones a topic cites | `id, title, family, what, when_to_use[], models[]` with `execution[]`, `invalidates[]`, `budget`, `success_metric[]` per entry |
| `data_quality/<model>/countries/<CC>.yaml` | per-country data-quality scorecards (generated), with `datasets.yaml`, `MATRIX.csv`, `INDEX.md` | |
| `baselines/<model>/` | the settled baseline `manifest.yaml` and its `config[.<variant>].yaml` overlays | |
| `policy/` | the energy policy registry (assets, targets, subsidies, regulation as CSV) and its tools | |
| `basemaps/` | admin0/admin1/land GeoJSON for the plot cards | |
| `models/<model>` | submodules, the version anchor every card cites | |
| `archive/` | the pre-restructure content the app does not read (see below) | |

## How the app reads it

A card is written once for every model it applies to. The app opens
`topics/<slug>.yaml`, picks the `models[]` entry whose `model` matches the
network in front of the user, and reads `coverage` and `gap_assessment` before
anything else. A topic is listed for a model only when it has an entry for it.
A model's entry names only recipes and methods that exist with an entry for
that model; `archive/tools/restructure.py --validate` enforces that and is the
check to run after editing. `plots[].id` refer to pypsa-app's own plot cards.
There is no version marker: everything outside `archive/` is current.

## archive/

Never read by the app. Holds, at their old relative paths: the v1 topic cards
of both models and their capability registries (`FUNCTIONALITY.yaml`), the v1
method essays, the unverified method specs, every `_qa` checker and evidence
file, the generated data-quality maps, the old per-model READMEs and indexes,
`fixtures/BASELINE.md` and the fixture network symlinks, plus
`tools/restructure.py`, the script that produced this layout.

## Checks

```
python3 archive/tools/restructure.py --validate
```

## Anchors

Earth cards cite the `models/pypsa-earth` submodule commit. Eur cards cite
`849c8858`, a fork branch commit that is not in any public remote; the
`models/pypsa-eur` submodule pin points at upstream. See
`archive/fixtures/BASELINE.md`.
