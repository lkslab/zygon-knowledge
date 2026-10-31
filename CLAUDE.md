# CLAUDE.md

This repo is the knowledge base pypsa-app's assistant reads at runtime. It holds
YAML cards and CSV tables, and the app's `knowledge` package (`src/knowledge/` in
`pypsa-app`) parses them by path. Every edit to a card's shape or a directory name
is a contract change with that reader. `README.md` covers the layout and card shapes;
this file covers the link.

## How the app gets the repo

- The gitlink is the version pin. `pypsa-app` carries this repo as the submodule
  `src/pypsa_app/knowledge` (`.gitmodules`, `lkslab/zygon-knowledge`), and
  `KNOWLEDGE_ROOT` in `backend/settings.py` points at it. There is no runtime fetch.
- `make knowledge` runs `git submodule update --init src/pypsa_app/knowledge`; the
  Dockerfile refuses to build without it.
- App CI checks it out with `.github/actions/checkout-knowledge`, passing
  `secrets.KNOWLEDGE_REPO_TOKEN`. The pinned sha must be on this repo's `main`.
- Ship content by committing here, then in the app:
  `git -C src/pypsa_app/knowledge fetch && git -C src/pypsa_app/knowledge checkout <sha>`,
  `git add src/pypsa_app/knowledge`, commit.
- The read set is named twice: `[tool.setuptools.package-data]` in the app's
  `pyproject.toml` and the `src/pypsa_app/knowledge/**` re-includes in its
  `.dockerignore`. A new shipped directory needs both edited.
- Cards are re-read on every call, so an edit under the root shows on the next call.

## Who reads what

Handles are opened in `backend/services/agent/turn_input.py` (per turn),
`backend/services/study/gate.py` and `scripts/preflight.py`: `Knowledge.open(root, model)`
once per model, `Policy.open(root)` once.

| tree here | `knowledge` API |
|---|---|
| `topics/<slug>.yaml` | `topics()`, `topic(slug)` |
| `carriers/<book>/<slug>.yaml` | `carriers()`, `carrier(...)` |
| `methods/<slug>.yaml`, `methods/<slug>/spec.yaml` | `methods()`, `method(slug)` |
| `data_quality/<model>/countries/<CC>.yaml` | `data_quality_cards()`, `data_quality(...)` |
| `version_anchor` of every section | `anchors()`, the ref per card id |
| `policy/*.csv` | `Policy`: tables `assets`, `targets`, `subsidies`, `regulation` through `query`, plus `coverage`, `blocs`, `technology_taxonomy` (`resolve_technology`) |
| `models/<model>`, `tools/`, `policy/tools/`, `policy/_qa/`, `policy/sources.csv` | nobody at runtime |

What the app does not do:

- It applies no `payload/` trees since pypsa-app #296 (bundles are config-only). A later
  feature re-adds payload application with a contract; the trees stay for it.
- It branches on no `execution[].kind`.
- Its basemaps are its own; none live here.

## Cross-repo ids

Edit the app together with this repo when one of these changes:

- `Model`: `pypsa-eur`, `pypsa-earth` (`src/knowledge/cards.py`).
- `CarrierBook`: `generation_conversion`, `demand` (`cards.py`).
- `Rung`: `L0`..`L5` on carrier `boundary[]` (`cards.py`).
- `Table`: `targets`, `assets`, `subsidies`, `regulation`, and `Coverage`: `complete`,
  `partial`, `seed`, `missing` (`src/knowledge/policy.py`).
- Method ids a topic names must resolve to a method with a section for that model; the
  validator also rejects a method no topic cites.

## Anchors

Every topic, carrier and method section cites `version_anchor.ref`. Current refs:

- pypsa-eur `09e8910ae03ace9af8ff821514cda7822fdd473f` (`2026-10-12`), the `lkslab/pypsa-eur`
  fork commit the app runs. It equals the `models/pypsa-eur` gitlink, the app's
  `workflows/pypsa-eur` gitlink and the profile `pinned_ref`.
- pypsa-earth `8435f4c8cc05f30088933b37b7db497ff860dc53`, equal to `models/pypsa-earth`.

The app's `tests/test_preflight_real_tree.py` requires profile `pinned_ref`, the
`workflows/pypsa-eur` gitlink and every eur anchor to agree (`pin_trio` in
`scripts/preflight.py`). To bump eur when the app pins a new fork commit:

1. `git -C models/pypsa-eur fetch origin dev && git -C models/pypsa-eur checkout <sha>`.
2. Set `ANCHORS` in `tools/validate.py`.
3. One `sed` over every eur `version_anchor`: replace the old ref and its `date:`.
4. Run the validator and `tools/resolve_eur_citations.py`.
5. Bump the app's gitlink for this repo in the commit that bumps its fork pin.

History of the eur anchor: `849c8858` until 2026-09-10 (fork branch, no public remote);
upstream `a6c45e5a` from 2026-09-10; fork pins from 2026-10-09; `09e8910a` since 2026-10-12.

## Checks to run after editing

```
uv run --no-project --python 3.13 --with pyyaml --with pydantic python tools/validate.py --app <pypsa-app checkout>
uv run --no-project --python 3.13 --with pyyaml --with pydantic --with pytest pytest tools
python3 tools/resolve_eur_citations.py   # needs: git submodule update --init models/pypsa-eur
```

Inside the app's submodule path the validator finds the app by itself, so `--app` is optional there.
