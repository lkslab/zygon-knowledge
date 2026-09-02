# zygon-knowledge

The knowledge base behind the pypsa-app assistant: cookbooks, the
energy_brockhaus policy registry, baseline fixtures and basemaps, extracted
from the archived zygon prototype. pypsa-app pins one commit of this repo and
fetches it on first use.

## Layout

```
cookbooks/              topic cards, recipes, methods, data-quality scorecards
  methods/              executable method specs (v2) and v1 essays
  pypsa-eur/            topics/ generation_conversion/ demand/ data_quality/
  pypsa-earth/          same four books
  _qa/                  provenance index, upstream-impact, shared card checks
data/energy_brockhaus/  policy registry (assets, targets, regulation, subsidies)
fixtures/recipes/       baseline manifests and configs per model
fixtures/networks/      symlinks into models/ (artifacts are not tracked)
basemaps/               admin0/admin1/land GeoJSON for the plot cards
models/pypsa-eur        submodule, the version anchor every eur card cites
models/pypsa-earth      submodule, the version anchor every earth card cites
```

## Checks

All `_qa` scripts run from the repo root, e.g.

```
python3 cookbooks/pypsa-eur/topics/_qa/check_topics.py
python3 cookbooks/methods/_qa/check_methods.py
python3 cookbooks/_qa/build_provenance_index.py
python3 cookbooks/_qa/upstream_impact.py --model pypsa-eur --to <ref>
```

`upstream_impact.py` needs the submodules checked out. Bumping a submodule pin
is an epoch bump: run it first, then re-anchor the cards it reports as broken.
