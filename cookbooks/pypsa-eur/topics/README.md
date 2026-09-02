# Topics cookbook — planning-question wiring cards (pypsa-eur)

The other books are organized by *thing* (technology, demand kind, dataset).
This one is organized by *question*: the 100 planning/analysis topics of
Appendix A in `energy_topics/energy_modelling_demand_landscape.md`, ranked by
global urgency (rank 1 = transmission expansion planning … rank 100 = tidal),
plus zygon-native extensions at ranks > 100 (101 = marginal price prediction)
for questions the interviews needed that the paper's ranking never carried.
The rank↔slug↔title universe is pinned in `cookbooks/_qa/topic_card_lib.py`
and is SHARED with the pypsa-earth book — the two books answer the same
questions for their respective models, so diffing a card across them shows
exactly where the models differ.

A card does not re-derive anything — it **wires** a topic to what already
exists.

## The gate: v2 or it can't scope a study

Cards are being migrated one at a time to the v2 format, marked by
`schema_version: 2` (the same convention `cookbooks/methods/` uses). **A card
without that marker cannot scope a study** — the topic is real, the wiring for
it is not written yet, and the honest move is to say so and stop. INDEX.md's
`v` column says which is which; `**Migrated: N v2 / M v1**` in its footer is
the running score.

Normative field reference: `cookbooks/_qa/TOPIC_CARD.schema.yaml`.
Authoring: copy `cookbooks/_qa/TOPIC_CARD.template.yaml`.

## What a card wires

Both generations:

1. **`recipes:`** — the generation_conversion / demand recipes the topic draws
   on (slugs validated against the actual books in this repo). Boundary
   ladders live there.
2. **`gap_assessment`** — how far the standard pypsa-eur workflow gets on this
   topic today and what would need building; `coverage: ready | partial | gap`
   is the one-word verdict. See `INDEX.md` for the ranked table.

v2 only:

3. **`methods:`** — links into `cookbooks/methods/`, resolved to real v2
   EXECUTABLE specs carrying a section for this model. This is the edge that
   terminates in something runnable: a bundle may cite a v2 method spec, and
   may not cite a v1 essay, so a card may not point at one either. The checker
   warns (does not fail) when a linked spec is still `draft` here — INDEX.md
   marks those `*`. At interview time the verified-only rule applies: a draft
   method does not exist as far as promises to the user go.
4. **`defaults:`** — an axis where the SHIPPED config is already the answer,
   so there is no spec to cite (e.g. overnight foresight). Recorded as data,
   not prose, so it is greppable and checkable.
5. **`plots:`** (optional) — the presentation edge, for topics whose
   deliverable is a figure/statistic set: ids resolved against `plots/<id>.py`
   (plot cards are executable, so the edge terminates in something runnable).
   The mandatory checkpoint figures stay routed by `plots/INDEX.md`; this
   edge names only the cards that ARE the topic's answer.

v1 only (legacy, retained until migration completes):

6. **`functionality:`** — references into `FUNCTIONALITY.yaml`, the registry
   of pypsa-eur model *capabilities* (analysis machinery, not technologies):
   wildcard grammar, solve-time constraints, foresight modes (incl. perfect
   foresight and the operations-only solve), clustering, scenario management,
   outputs — each with a grep-verified `consumer` (file:symbol) and a status:
   `working | partial | dead-key | absent`. Absent entries name the nearest
   workaround; dead-key entries document config keys that exist but are read
   by nothing (or crash when used). v2 drops this edge: a registry of prose
   capability descriptions can never make a promise the referee keeps.

## How an agent uses this

Start here when the user brings a *question* ("can we retire these coal plants
early?", "what does zonal pricing change?"). Check `v` first. On a migrated
card, it names the recipes to open next, the methods that execute the study
shape, and — where country data gates the answer — points at the
`data_quality` scorecards.

## Regenerate / verify

```bash
python3 cookbooks/pypsa-eur/topics/_qa/check_topics.py     # QA: cards + registry
python3 cookbooks/pypsa-eur/topics/_qa/generate_index.py   # rebuild INDEX.md
```

`check_topics.py --registry-only` validates only `FUNCTIONALITY.yaml` (useful
while cards are in flight). The full QA pins rank↔slug↔title against the
canonical Appendix A list, validates every cross-reference against the other
books, resolves every v2 `methods:` link, and grep-verifies every registry
consumer symbol. Both scripts are thin drivers over `cookbooks/_qa/`; the
logic is shared with pypsa-earth. Version anchor: `849c8858` (2026-07-23).

Because `methods:` links are resolved mechanically, **renaming a method breaks
topic-card QA** — re-run both books' `check_topics.py` after any change under
`cookbooks/methods/`. That coupling is the point.
