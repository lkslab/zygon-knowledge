# CLAUDE.md

This repo is the knowledge base that pypsa-app's assistant reads at runtime. It holds no
code the app imports; it holds YAML cards, CSV tables, config overlays and GeoJSON that the
app's loaders parse by path. Every edit here is a contract change with a consumer in
`../pypsa-app`, so read this file before touching a card's shape or a directory name.

The README covers the layout and the card schemas. This file covers the linkage: which app
module reads which tree, what each reader assumes, how a version ships, and where the two
repos currently disagree.

## How the app gets this repo

- **Git submodule, shipped as package data.** `pypsa-app` carries this repo as the submodule
  `src/pypsa_app/knowledge` (`.gitmodules`, url `lkslab/zygon-knowledge`). The gitlink is the
  version pin: `backend/settings.py` hard-codes `KNOWLEDGE_ROOT` to that directory and
  `settings.knowledge_path` returns it. There is no runtime fetch, no `KNOWLEDGE_REV`,
  `KNOWLEDGE_DIR` or `KNOWLEDGE_PINNED` (removed in app commit `8c504f6`, 2026-09-10). The
  Docker image and the wheel refuse to build without `topics/` under that path (`make knowledge`
  initialises it). Submodules under `models/` are never initialised there.
- **Content edits are live.** Cards are parsed on every call and the one cache
  (`registry.py`) is mtime-keyed, so an edit under the resolved root is visible on the next
  tool call, no restart needed. Only changing *which* directory is the root needs a restart.
- **Local work happens in this checkout.** Two ways to point the app here, both gitignored on
  the app side. Local mode (`uv run pypsa-app ...`, what this machine runs): `KNOWLEDGE_DIR=`
  `/home/lukas/Desktop/zygon-knowledge` in `pypsa-app/.env`, read by `settings.knowledge_dir`
  on the next start. Docker dev stack (`make dev`): `compose/compose.local.yaml` bind-mounts
  `../zygon-knowledge` over the submodule path in the `api`, `prefect-worker`,
  `snakedispatch` and `agent` containers; the Makefile layers it on when present.
- **Branches.** This repo works on `main` only: commit here, push `main`. The app works on
  `main` plus a long-running `dev` branch (one PR onto `main`, rebased now and then).
- **Shipping content** means pushing `main` here, then on the app's `dev`:
  `git -C src/pypsa_app/knowledge fetch && git -C src/pypsa_app/knowledge checkout <sha>`,
  `git add src/pypsa_app/knowledge`, commit. The sha must be on `origin/main` of this repo or
  CI's submodule checkout fails. The app's test suite runs against
  `pypsa-app/tests/fixtures/knowledge/`, a miniature of this layout, so a shape change needs
  the fixture updated in the same app commit.

## Who reads what

The nested agent that queries this repo is the **scoper** (`pypsa-app/src/agent/scoper.py`).
It is dispatched by the consultant's `scope_question` tool and has six tools, all implemented in
`knowledge_tools.py` over the pure loaders in `knowledge.py`. The consultant itself never opens
a card.

| tree here | app reader | what it assumes |
|---|---|---|
| `topics/<slug>.yaml` | `knowledge.list_topics` / `load_topic`; scoper tools `list_topics`, `get_topic_card` | One file per topic, `models[]` with one entry per model. A topic is listed for a model only when it has an entry. `get_topic_card` returns `approach`, `trade_offs`, `limitations` first, then `methods[]`, `defaults[]`, `plots[]`, `version_anchor`. There is no coverage verdict: every listed topic can be modelled; the consultant affirms the study from `approach`, raises each `trade_offs` entry (where a study spends resolution, compute and scenarios) at the interview question it bears on, and states `limitations` once at the end of the interview. |
| `carriers/generation_conversion/`, `carriers/demand/` | `knowledge.list_carriers` / `locate_carrier`; scoper tools `list_carriers`, `get_carrier` | The two book names are hard-coded as `CARRIER_BOOKS`. Card ids must be unique across both books, since `get_carrier` searches both when no book is given. `list_carriers` returns id and title only, on purpose, because the scoper reads the whole list (~150 rows) before opening a card. The model section's `boundary[].rung` is what decides `executable`: only L0 and L1 run in the current deployment. |
| `methods/<slug>.yaml` or `methods/<slug>/spec.yaml` | `knowledge.load_method`; scoper tool `get_method` | Resolved flat file first, then directory spec. The scoper only opens methods the topic card names. `payload/<model>/` trees are not read by the scoper; the referee's `method_payload` handling is still deferred in the app (`config_static.py` reports `payload-deferred`). |
| `data_quality/<model>/countries/<CC>.yaml` | `knowledge.load_country`; scoper tool `get_data_quality` | Whole document returned, keyed by upper-cased ISO2 (per-family roll-up across many countries). The scoper calls this first; grade `C` (a borrowed number) is the model's routine condition and is never a flag on its own, a flag is a grade `D` (the feature silently disappears) on a family the question rests on, so a mainstream question on pypsa-eur's full set carries none. The brief keeps every family's worst grade for follow-up questions. Cards carry `families[].grade` and `datasets`, no top-level `overall`. `datasets.yaml`, `MATRIX.csv`, `INDEX.md` are not read by the app. |
| `policy/*.csv` | `agent/registry.py`, `policy_tools.py`, dispatched as the **policy researcher** subagent (`research_policy`) | Tables `assets`, `targets`, `subsidies`, `regulation`, plus `coverage`, `blocs`, `technology_taxonomy`. Same checkout, same `ensure_root`. `record_id` values are what `report.md` refs comments cite and the referee checks. `policy/tools/`, `_qa/`, `_work/` are not read. |
| (no `baselines/`) | `backend/services/agent/model_profile.py` | Removed 2026-09-11: the app runs no reference config. Its target/verify templates and the solver overlay are app-owned constants, every study folds onto the checkout's own `config/config.default.yaml`, and a method section's `execution[kind: config]` entries are applied by the app underneath the bundle's changes. Method sections no longer carry a `baseline:` field. |
| `basemaps/_land50m.json`, `_admin1_10m.json`, `_admin0_50m.json` | `backend/services/agent/plots.py` passes the dir as `--basemaps` to `plots/style.py` | Exact file names are hard-coded in the app. Missing dir degrades to a labelled fallback rather than failing. |
| `models/<model>` submodules | nobody at runtime | The version anchor the cards cite. See Anchors below. |
| `archive/` | nobody | Pre-restructure content. `archive/tools/restructure.py --validate` is the schema check. |

Two more app readers open the same files without going through the scoper:

- **Referee citations** (`backend/referee/citations.py`, `network_asserts.py`, `config_static.py`)
  resolve a bundle's `justified_by: {book, card, rung}` by loading the carrier card and checking
  the rung sits on that model's `boundary` ladder. Rung L0/L1 map to `config` changes, higher
  rungs to code/data/rule changes. `network_asserts` also looks for a `section.asserts[]` list
  keyed by boundary `variant` and `stage`; no carrier card in this repo carries one yet, so that
  check always skips with `no-asserts`.
- **The Context tab** (`backend/services/agent/knowledge_docs.py`) replays what a turn read at
  `topics/<slug>`, `carriers/<book>/<slug>`, `methods/<slug>`, `policy/<CC>/<table>`, naming the
  source file. It still accepts the pre-rename `recipes/` path so stored sessions replay.

## Cross-repo ids that must stay in sync

- **Carrier books**: `generation_conversion`, `demand`. Adding a third book means editing
  `CarrierBook` in the app.
- **Models**: `pypsa-eur`, `pypsa-earth`. Both the app's `Model` literal and the validator's
  `MODELS` tuple hard-code them.
- **Coverage vocabulary**: `ready`, `partial`, `gap`, `unknown` (app), enforced by the validator.
- **Rungs**: `L0`..`L5` on carrier `boundary[]`. The app's kind-rung matrix lives in
  `backend/referee/bundle.py`.
- **Plot ids** in `topics/*.yaml` `plots[].id` must exist under `pypsa-app/src/pypsa_app/plots/cards/`.
  Currently cited: `marginal_prices`, `price_duration`. Both exist.
- **Method ids** a topic names must resolve through `load_method` with a section for that
  model. The validator enforces this and also rejects any method no topic cites.
- **Topic slugs** are a fixed list in the validator (`TOPIC_SLUGS`). Adding a topic means
  editing `archive/tools/restructure.py` too, or the validate step fails.

## Anchors

Every card section cites a `version_anchor.ref`. The validator requires the canonical one per
model. Earth cards cite `8435f4c8`, which is also the `models/pypsa-earth` submodule pin. Eur
cards cite `a6c45e5a2d926ba9a5566cba24d905cff9f89939`, upstream `PyPSA/pypsa-eur` master
("Streamline workflow" #1838, 2026-09-09), which is also the `models/pypsa-eur` submodule pin;
`tools/validate.py` checks the two agree. The canonical eur sha lives in `tools/validate.py`
(`EUR_ANCHOR`), not in the frozen `archive/tools/restructure.py`.

What a6c45e5 means for card content: there is no `scenario` block and no wildcard
(`{clusters}`, `{opts}`, `{sector_opts}`, `{ll}`); cluster count is
`clustering.cluster_network.n_clusters`, time resolution `clustering.temporal.averaging`,
horizons the top-level `planning_horizons` list, CO2 the top-level `co2_budget` block
(`electricity.co2limit*` is gone). The rule graph is build_* -> `cluster_network` ->
`compose_network` (rules/compose.smk: add_electricity, prepare_sector_network,
prepare_network, brownfield/perfect, CO2 budget, adjustments in one rule) -> `solve_network`
(rules/solve.smk). Networks are `resources/<run>/networks/composed_<horizon>.nc` and
`results/<run>/networks/solved_<horizon>.nc`; resource files carry no cluster suffix.

Until 2026-09-10 the eur anchor was `849c8858`, a commit on the fork branch
`endogenous-industry-heat` (LukasFrankenQ/resilient-pypsa-eur, not on any public remote).
Its endogenous temperature-banded industrial process heat (`sector.industry_t`,
`build_industry_sector_ratios_endogenous.py`, `add_t_industry*`) is not upstream; the cards
now describe it as absent (`industry-process-heat-endogenous` eur section is a gap, the
industry cards re-rung those asks as L4 code changes naming the fork branch).

## Current state of the link (as of 2026-09-10)

- **Pins.** The app's `origin/main` gitlink points at `ffb1d8e`, its `dev` branch at
  `499ccfd`; both are on `main` here. Between app commit `32f57ae` (readers switched to
  `carriers/`) and `24af385` the pin sat at `8809a8c`, a commit that still had `recipes/`, so
  any deployment built from that window saw no carrier cards. When changing a directory name
  or card shape again, bump the gitlink in the same app commit that changes the reader.
- **Eur content re-anchored to upstream a6c45e5 on 2026-09-10, nothing re-run.** Every
  pypsa-eur section (146 carrier cards, 7 topics, 12 method docs, data_quality, the
  seven payloads) was rewritten against the streamlined workflow and passes
  `tools/resolve_eur_citations.py` with zero unresolved citations, but no baseline has been
  rebuilt and no `success_metric` evaluated on an a6c45e5 install. This is the one place
  that caveat is recorded: the topic cards no longer carry it (the sentence was a
  maintainer note, not a limitation of the modelling, and was dropped from the four eur
  sections that had it when `pitfalls` split into `trade_offs` and `limitations` on
  2026-09-13). `storage-dispatch` and `transmission-planning` dropped to
  `partial`, `clean-procurement` stays `partial`. The `baselines/` tree and the method
  sections' `baseline:` fields were removed on 2026-09-11 when the app dropped baseline runs
  (see the layout table). pypsa-earth content was not touched (earth sections and trees are
  byte-identical).
- **Payload patches rebased.** All 14 `methods/*/payload/pypsa-eur/edits/*.patch` apply
  cleanly to a6c45e5 (`git apply --check`); the payload rule files read
  `networks/composed_{horizon}.nc` and keep the `{horizon}` wildcard because
  `solve_network.py` reads `wildcards.horizon`. The schema allows extra top-level config keys
  (`extra="allow"`), so the payload config blocks pass validation.
- **No `asserts` on any carrier card**, so the referee's network-asserts check is inert.
- **Payload trees are shipped but not consumed.** `methods/*/payload/<model>/` is materialised
  by zygon, not yet by pypsa-app.
- **Three eur-only methods added 2026-09-10, unverified by an eval run.** `hourly-matching`
  (payload `zygon_cfe`: consumer + palette builder, the matching hook, the collector),
  `annual-matching` (a spec that shares that payload, no payload dir of its own) and
  `storage-economics` (payload `zygon_storage_economics`). Their scripts were exercised
  standalone against the settled baselines at the previous anchor (constraint rows counted per
  window, cost-recovery identity checked) but no `success_metric` has been evaluated by the
  referee, and nothing has run on a6c45e5.

## Checks to run after editing

```
python3 tools/validate.py                # schema check with the current anchors
python3 tools/resolve_eur_citations.py   # every eur citation resolves in models/pypsa-eur
```

`archive/` is frozen. `archive/tools/restructure.py --validate` still works but rejects the
current eur anchor; `tools/validate.py` wraps it. The resolver needs the eur submodule checked
out (`git submodule update --init models/pypsa-eur`).

To see the app read the working copy: nothing, if the server is already up with
`KNOWLEDGE_DIR` (local mode) or `compose/compose.local.yaml` (Docker) pointing here, since
cards are re-read per call. Otherwise restart it: `cd ../pypsa-app && uv run pypsa-app ...`
or `make dev`.
