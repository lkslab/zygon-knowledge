# Methods cookbook

Knowledge about **how energy systems are modelled** — the method layer, extracted from
the 100-paper PyPSA corpus in `papers/` and grounded against both model submodules.

## The fourth axis

The other books are keyed differently, and the difference is the point:

| book | keyed by | answers |
|---|---|---|
| `topics/` | QUESTION | "how much storage does this system need" |
| `generation_conversion/` | THING | "grid-scale batteries" |
| `demand/` | THING | "electricity load" |
| **`methods/`** | **HOW** | **"myopic optimisation", "MGA", "balancing market simulation"** |

An interview reaches for this book when the user's question is a *how*, not a *what*:
*should this be myopic or perfect foresight · how many nodes · how do we handle
uncertainty · can you simulate the balancing market · how do I know the model is right.*
The literature is made of these choices, and nothing else in the cookbooks covered them.

35 methods in 9 families. See `INDEX.md` to route, `PREVALENCE.md` for what the field
actually does, `PRIMITIVES.md` for the capabilities that are one wrapper away.

## What this book is NOT

**It does not re-derive model capabilities.** `cookbooks/<model>/topics/FUNCTIONALITY.yaml`
already owns those — 105 grep-verified entries for pypsa-eur, 68 for pypsa-earth, each
with `status` / `surface` / `consumer`. A method card CITES those ids in
`models[].functionality[]`, and `check_methods.py` resolves every one.

The book adds the five things that registry structurally cannot hold:

1. **the literature definition** — what the method is called, by whom, and what it answers
2. **the procedure** — the algorithm as practised, step by step, each step naming the
   callable that performs it (or `null`, which is how a card says "this step is the work")
3. **the variants** — the distinguishable ways it is done, each with its own rung
4. **the prevalence** — how much of the corpus uses it, with the evidence attached
5. **the assembly** — for a method that is several registry surfaces wired together, the
   ordered recipe. `balancing-and-ancillary-services` is four registry entries, none of
   which alone is the method.

## The four verdicts, and the one idea worth remembering

Every model section opens with `available.verdict`:

- **`turnkey`** — a config flip runs the method
- **`assemble`** — every surface exists; you wire them (see `assembly`)
- **`primitive-only`** — PyPSA the library has it; the workflow does not expose it
- **`absent`** — neither layer has it; this is new formulation work

> **A primitive one layer down turns L5-from-scratch into L5-with-a-handle.**

That is the book's single most useful idea. `pypsa_primitive` records it per method,
separating two facts that look like one: *the primitive exists* and *the workflow can
reach it*. Seven of 35 methods have a PyPSA primitive that neither workflow exposes —
`optimize_mga`, `optimize_security_constrained`, `network_lpf_contingency` and others.
Those are collected in `PRIMITIVES.md`, which is a roadmap rather than an index: each row
is a driver script away, not a research project. The contrast case is instructive —
`optimize_with_rolling_horizon` is the same kind of primitive, and pypsa-eur *does* expose
it through `solving.options.rolling_horizon`, so that method is L1 and MGA is L5.

## The corpus, and its bias

100 PDFs: `papers/tier1_core_group/` (64, Tom Brown's group at TU Berlin and immediate
collaborators) and `papers/tier2_ecosystem_community/` (36, derived models, core tools and
independent groups). Roster in `papers/INDEX.csv`; the machine-readable version this book
validates against is `_qa/CORPUS.yaml`.

**The corpus is PyPSA-centric and therefore over-represents this one community's
methods.** Where a whole family of practice is thin or absent here — stochastic
programming, unit commitment, explicit market mechanisms, probabilistic adequacy — that
is a fact about the corpus as much as about the field, and the affected cards say so in
`prevalence.basis`. Prevalence should be read as "what this literature does", never as
"what is worth doing".

`papers/` is gitignored (663 MB), so on a fresh clone `literature[].paper` verification
degrades to a warning until `sweep_corpus.py` has run.

## Card anatomy

Full field contract in `_qa/METHOD.schema.yaml`; deltas from
`contracts/RECIPE.schema.yaml` and the reasoning in `_qa/SCHEMA_NOTES.md`. In short:
kept `id`/`title`/`summary`/`when_to_use`/`levers`/`boundary`/`where`/`data_dependencies`;
replaced `out_of_box` with `available` and `asserts` with `verifies`; dropped
`invalidates`; added the literature side plus `functionality`, `assembly`, `cost_profile`.
`asserts`, `invalidates` and `out_of_box` are **rejected** by the checker rather than
ignored, so a card pasted from a recipe fails loudly instead of being mis-executed by the
existing referee.

One card carries both model sections, `pypsa-eur` first. Both are required —
`not_applicable: <reason>` is the escape, never omission.

## How an agent uses this

1. Topic card first (unchanged — `context/CONTEXT.md` steps 1–3).
2. If the question is a HOW, open **one** method card. Cards are ~200 lines against a
   topic card's ~50; load one, never two.
3. Read `available.verdict` and the `boundary` rung for the user's variant. That routes
   the bundle exactly as a recipe's ladder does: L0/L1 → config change, L2+ → diff.
4. `assembly` tells you which surfaces and recipes to combine; `cost_profile` tells you
   what to promise about runtime *before* promising it.
5. `pitfalls` is what to say out loud. Many of these methods run happily and answer the
   wrong question.

**Never browse this book.** Route via `INDEX.md`'s `when_to_use`, then stop.

## Provenance and version anchors

Every model claim carries `provenance: file:symbol`, grep-verified, **never a line
number**. Literature claims carry an exact paper filename instead.

- `models/pypsa-eur` @ `849c8858d2536ccf8eed0c2e838d22a474a7ee5d`
- `models/pypsa-earth` @ `8435f4c8cc05f30088933b37b7db497ff860dc53`
- pypsa `0.30.3` — a **soft** anchor: a version string, not a SHA, because pypsa is a
  conda dependency rather than a submodule

`check_methods.py` reads the live SHAs from `git submodule status`, so when a submodule
moves, every card fails until its claims are re-verified and restamped.

## Regenerate / verify

```bash
PY=~/Desktop/earth/pypsa-earth/.pixi/envs/default/bin/python   # or any python3 + pyyaml

python3 cookbooks/methods/_qa/sweep_corpus.py       # PDFs -> _qa/text/, SWEEP.csv, CORPUS.yaml
python3 cookbooks/methods/_qa/pivot_evidence.py     # paper_methods/ -> EVIDENCE.yaml + INDEX
python3 cookbooks/methods/_qa/check_methods.py      # MUST exit 0 — the golden rule, mechanically
python3 cookbooks/methods/_qa/generate_index.py     # INDEX / PREVALENCE / PRIMITIVES
```
`check_methods.py --only <slug>` for one card. `PYPSA_ENV=<path>` to point at a different
pypsa install. The checker resolves everything from its own location, so unlike the
ported per-model checkers it needs no hardcoded sibling paths.

## How the book was built

Each paper was read exactly once and each card written exactly once, with a pivot
between — 100 papers x 35 methods would otherwise be 3500 readings that disagree.

`_qa/sweep_corpus.py` (regex screen, reproducible) → `_qa/paper_methods/<paper>.yaml`
(one record per paper) → `_qa/pivot_evidence.py` inverts to `_qa/EVIDENCE.yaml` (one slice
per method) → `_qa/RECONCILE.md` freezes the slug list → one card per slice, grounded
against the submodules.

`_qa/PASS1_INSTRUCTIONS.md` and `_qa/PASS2_INSTRUCTIONS.md` are the specs used, kept so
the book is rebuildable rather than a one-off artefact.

## Not yet built

- **`verifies` has no executor.** `referee/check_ensemble.py` does not exist; the field is
  authored (301 checks) so it is there when the referee catches up. Several checks are
  written to FAIL at the current refs, deliberately, to pin a defect.
- **`topics/` cards have no reciprocal `methods:` field**, so step 2 above is a judgement
  rather than a lookup. That is a 100-card edit per suite plus a `check_topics.py`
  extension.
- **`contracts/BUNDLE.schema.yaml` does not accept `book: methods`** in `justified_by`.
  L5 method work is exactly the case where no recipe exists to cite, so this probably
  should be allowed — but it is a contract change, i.e. breaking.
- **`_qa/GAPS.md` (667 lines)** is the honest to-do list the authoring produced: registry
  ids that should exist, dead keys found, evidence too thin to ground a field, and
  fixtures that would let a `verifies` check actually run. It is ranked work, not noise.

## Authoring payloads (dir-form v2 methods) — composability rules

Learned building `flow-based-market-coupling` + `redispatch` +
`investment-geography` (2026-08-02), which compose in ONE bundle:

- **File-disjoint or nothing.** Every payload ships its OWN scripts and its
  own new rule file; shared substrate is DUPLICATED per payload (a payload
  must apply standalone). Two payloads never ship the same `new/` path.
- **At most one EOF-append per patched file across all composable
  payloads.** GNU `patch` anchors a hunk with no trailing context to
  end-of-file, so two EOF-appends to `config.default.yaml` (or the earth
  Snakefile) cannot compose. Prefer mid-file insertions at DISTINCT unique
  anchor lines with trailing context; verify both application orders with
  `patch -p1` on scratch copies before shipping (pathway-perfect already
  holds earth's Snakefile EOF slot).
- **New config keys ride the payload's config.default.yaml patch** — the
  referee (`check_config`) and QA (`check_method_exec`) resolve config
  steps against the payload-patched view (`common.payload_patched_config`,
  `payload_view`) and grep payload files for consumers. eur's pydantic
  validation tolerates new top-level sections (`extra="allow"`).
- **Snapshot windows are method-config, not global.** Slice inside the
  payload's scripts; the global `snapshots` key is budget-pinned and
  touching it rebuilds the whole profile chain.
- **Artifacts are pypsa networks with `n.meta['<method>']` summaries** —
  success metrics read meta plus raw network data; the bundle's
  `invocation:` adds the new DAG head and `replace_verify_networks` makes
  it THE solved artifact `check_method` binds to.
