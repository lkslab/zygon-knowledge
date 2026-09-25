# zygon-knowledge

The assistant's knowledge base for pypsa-app. The app pins one commit of this
repo (`KNOWLEDGE_REV` in its `src/agent/knowledge.py`) and reads the cards
below at runtime; bump the pin to ship new content.

## Layout

| path | what | shape |
|---|---|---|
| `topics/<slug>.yaml` | one card per planning question, seven of them | `id, title, question, when_to_use[], models[]` where each `models[]` entry is `{model, approach, trade_offs[], limitations[], methods[{id, role}], defaults[], plots[], version_anchor{ref, date}}` |
| `carriers/generation_conversion/<slug>.yaml`, `carriers/demand/<slug>.yaml` | carrier cards: one per technology or demand segment, shared across models | `id, title, summary, when_to_use[], models[]` where each entry is `{model, version_anchor, out_of_box, levers[], boundary[{variant, rung, note}], where[], data_dependencies[]}` |
| `methods/<slug>.yaml` or `methods/<slug>/spec.yaml` + `payload/<model>/` | executable method specs, only the ones a topic cites | `id, title, family, what, when_to_use[], models[]` with `execution[]`, `invalidates[]`, `budget`, `success_metric[]` per entry; an `execution[]` entry is `{kind: config, key, value}` (folded into the run's base config), `{kind: payload, source?}` (the tree under `payload/<model>/` beside the card, or beside the card `source` names: `new/**` copied onto the checkout verbatim, `edits/*.patch` applied to the pinned commit), `{kind: invocation, note}` (the extra targets and verify networks the bundle declares); `code` and `data` entries are prose and make the method non-executable until shipped as a payload |
| `data_quality/<model>/countries/<CC>.yaml` | per-country data-quality scorecards (generated), with `datasets.yaml`, `MATRIX.csv`, `INDEX.md` | |
| `policy/` | the energy policy registry (assets, targets, subsidies, regulation as CSV) and its tools | |
| `basemaps/` | admin0/admin1/land GeoJSON for the plot cards | |
| `toymodels/index.yaml`, `toymodels/<slug>/` | 35 minimal runnable PyPSA models, one per concept (dispatch and prices, networks and congestion, unit commitment, storage and hydro, expansion and pathways, uncertainty, markets and subsidies, sector coupling and carbon, model reduction and debugging), for back-of-the-envelope answers and figures; see `toymodels/README.md` | `card.yaml` (`id, title, summary, concepts[], answers[], builds_on[], setup, method, knobs[], figures[], numbers[], limitations[], sources[], pypsa`), `model.py`, generated `results.yaml`, `figures/<id>.json` (pypsa-app figure.json bundles), `preview.html` |
| `models/<model>` | submodules, the version anchor every card cites | |
| `archive/` | the pre-restructure content the app does not read (see below) | |

## How the app reads it

A card is written once for every model it applies to. The app opens
`topics/<slug>.yaml`, picks the `models[]` entry whose `model` matches the
network in front of the user, and reads `approach`, `trade_offs` and
`limitations` before anything else: `approach` says how the model treats the
question (what it represents natively and where the levers live);
`trade_offs` are the choices about where a study spends its resolution,
compute and scenarios and what it can then say, which the consultant raises
at the interview question each bears on (a time-step trade-off with the
temporal resolution question); `limitations` are what the model does not
represent or gets wrong out of the box, which the consultant states once, at
the end of the interview. The consultant affirms the study from `approach`.
There is no coverage verdict: every topic with an entry for a model can be
modelled on it, and a topic is listed for a model only when it has one.
Topics do not name carrier cards: the app lists `carriers/<book>/` and opens a
card on demand, and every carrier card carries a section for each model it
applies to. A topic's `methods[]` names only specs that exist with an entry for
that model; `archive/tools/restructure.py --validate` enforces that, rejects a
`recipes:` key on a topic, and is the check to run after editing.
`plots[].id` refer to pypsa-app's own plot cards.
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
python3 tools/validate.py              # schema check (archive validator logic, current anchors)
python3 tools/resolve_eur_citations.py # every pypsa-eur citation resolves in models/pypsa-eur
```

`archive/tools/restructure.py --validate` is the original schema validator; `archive/` is
frozen and its `ANCHORS` constant still names the pre-2026-09 eur anchor, so
`tools/validate.py` imports it unchanged and overrides that one value. The resolver walks
the pypsa-eur section of every card and checks each `scripts/…:symbol`, `rules/…:rule` and
`config/config.default.yaml:key` citation against the submodule checkout; it needs
`git submodule update --init models/pypsa-eur`.

## Anchors

Both models' cards cite their `models/<model>` submodule commit. Eur cards cite
`a6c45e5a` (upstream `PyPSA/pypsa-eur` master, "Streamline workflow" #1838, 2026-09-09):
no `scenario` block or wildcards, `compose_network` -> `solve_network`, networks
`composed_<horizon>.nc` / `solved_<horizon>.nc`. Earth cards cite `8435f4c8`. Until
2026-09-10 the eur anchor was `849c8858`, a fork branch (`endogenous-industry-heat`) that
is not in any public remote; its endogenous industrial process-heat content was dropped
from the cards with the re-anchor. See `archive/fixtures/BASELINE.md` for the older history.
