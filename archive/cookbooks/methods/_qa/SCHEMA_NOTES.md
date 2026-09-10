# Schema notes — how the methods book differs from the recipe contract

Companion to `METHOD.schema.yaml`, in the spirit of
`cookbooks/pypsa-eur/demand/_qa/SCHEMA_NOTES.md`: the deltas against
`contracts/RECIPE.schema.yaml`, the reasons, and the deliberate exclusions. Read this
before harmonising the book with the others.

## 1. Two model sections per card, in one file

`methods/` is a SIBLING of `pypsa-eur/` and `pypsa-earth/`, not a child, so a card is
model-agnostic and carries both model sections. `generation_conversion/_qa/check_recipes.py`
asserts `len(models) == 1`; that is a per-model-directory artefact, not a contract rule
(the demand book already relaxes it), and `check_methods.py` asserts exactly TWO,
`pypsa-eur` first.

Both are REQUIRED, with `not_applicable: <reason>` as the escape rather than omission —
an omitted section is indistinguishable from an unexamined one, and the eur/earth
asymmetry is the payload of this book. In practice that asymmetry turned out to be the
single most useful thing the cards carry, and it runs in both directions: earth is ahead
on RFNBO temporal matching, Monte-Carlo sampling, discount-rate sweeps, low-voltage OSM
ingestion, GADM clustering and brownfield conversion of conventional generators; eur is
ahead on perfect foresight, transmission losses, operations-only re-solve, imports,
scenario matrices and nearly all sector detail.

## 2. Dropped fields, and why dropping beats reusing

| dropped | replaced by | reason |
|---|---|---|
| `out_of_box` | `available` | the question for a method is not "does the model represent this thing" but "can the workflow EXECUTE this procedure, and how much of it". `available.verdict` is a four-value enum an interview can read first; `available.missing` names the `procedure` steps with no handle. |
| `asserts` | `verifies` | `asserts` is a postcondition over ONE network `n`, and `referee/check_network.py` GLOBS the recipe books for it. A method's postcondition is usually over an ensemble ("N solutions, all within (1+eps)c*"), which no single `n` expresses. Reusing the name would have got method cards silently mis-executed by the existing referee. |
| `invalidates` | — | DAG invalidation is a property of a config/code CHANGE, not of a method. Methods above L1 are new driver scripts or run harnesses, about which `check_dag.py`'s settled-baseline diff has nothing to say. The recipes a method cites carry it. |

All three are in `check_methods.py`'s FORBIDDEN list and rejected with an explicit
message, so a card pasted from a recipe fails loudly instead of half-working.

## 3. Added fields

Literature side: `question` (deliberately the same field name as topic cards use — a
free harmonisation win), `aliases` (literature phrasing, distinct from `when_to_use`'s
user phrasing; the two feed different indexes), `family`, `prevalence`, `procedure`,
`variants`, `literature`, `pitfalls`, `requires_methods`, `combines_with`, `topics`,
`pypsa_primitive`.

Model side: `functionality` (ids into that model's `topics/FUNCTIONALITY.yaml`),
`assembly`, `cost_profile`, `verifies`.

Three of these earned their place beyond expectation:

- **`procedure[].handle: null`** makes a card self-summarising about where the L5 work
  is. The checker enforces that `handle` and `provenance` are null together.
- **`pypsa_primitive`** separates "the primitive exists" from "the workflow can reach
  it". 7 of 35 methods have a library primitive no workflow exposes; `PRIMITIVES.md` is
  generated from exactly that field and is the book's most actionable output.
- **`assembly`** is where the value sits for every `assemble`-verdict card, and it is
  the one thing `FUNCTIONALITY.yaml` structurally cannot hold: which registry surfaces
  to wire together, in order. `balancing-and-ancillary-services` is four registry
  entries none of which alone is the method.

## 4. `levers` is broader here than in a recipe

A recipe's `levers` are keys that tune the topic. A method card's include keys that
decide what the method would be applied TO, what it would cost to run, and which nearby
substitute exists — because for an `absent` or `primitive-only` method there is no key
that turns it on, and that information has nowhere better to live. Three cards converged
on this independently (`cascading-failure-analysis` annotates `lines.s_max_pu` as "not a
cascade lever, but the one config value that changes every cascade result"), so the
schema was widened to match rather than the cards narrowed to hide it.

Consequence: **a lever is not a claim that the method is available.** `available.verdict`
is the only field that claims that, and `check_methods.py` deliberately does NOT warn on
`verdict: absent` with levers listed. It DOES warn on `verdict: turnkey` when every
capability cited is `absent` from the registry — the one combination that is a real
contradiction.

## 5. Provenance resolution, and the one relaxation

`available`, `levers` and `where` resolve strictly against their own model's submodule.
`procedure` and `assembly` resolve against EITHER submodule OR the pypsa env, because
for a `primitive-only` method the assembly recipe legitimately is "call `optimize_mga`
from a driver" and there is no model-repo file to point at.

`pypsa_primitive.symbol` resolves against site-packages in the pypsa env. That is a
SOFT anchor — pypsa is a conda dependency, not a submodule — so it is pinned to a
version string (`0.30.3`) and the checker skips it with a warning when the env is
absent. `papers/` is gitignored, so `literature[].paper` verification also degrades to a
warning on a fresh clone until `sweep_corpus.py` has run.

## 6. Deliberate exclusions from the slug list

Recorded here so a future author does not "fix" them. See `RECONCILE.md` for the
pass-1.5 decisions and the evidence behind them.

- `transmission-losses` (1 paper) → a variant of `linearised-optimal-power-flow`.
- `brownfield` standalone → kept as its own card after all, because 20 papers use it and
  four other cards cite it as a prerequisite.
- `epsilon-cost-slack-constraint` → absorbed into `mga-near-optimal-space`'s procedure;
  a card whose only content is one constraint nobody retrieves separately.
- `linopy` as a method → the substrate card `custom-constraints-with-linopy`.
- `flow-based market coupling` (2 papers) → a variant of `zonal-nodal-and-redispatch`.
- `market-potential method` (2 papers) → a variant of `storage-sizing-and-duration`.
- 42 further one-off techniques stay out of the vocabulary and live in
  `EVIDENCE.yaml:unmatched_methods`, mined by pass-2 authors for `variants` and
  `procedure` detail. A card per one-off is a card nobody retrieves.

## 7. Known inconsistencies, left honest

- `sensitivity-and-uncertainty-sweeps` codes Schyska 2020 as `critiques` while pass 1
  coded it `defines`, so that card and `EVIDENCE_INDEX.md` disagree on one role. The
  checker's arithmetic is unaffected.
- Three cards (`stochastic-and-robust-optimisation`, `cascading-failure-analysis`,
  `endogenous-technology-learning`) count a paper in `prevalence` that another card also
  counts, where a paper's method genuinely spans two slugs (Grochowicz, Gazafroudi,
  Schyska). Paper counts across the book therefore sum to more than 810 claims.
  **Harmonisation should rule on this once rather than per card.**
- `variants[].papers` is constrained to be a subset of `literature[].paper`, so a
  variant whose only evidence sits in `unmatched_methods` carries an empty `papers`
  list. Several cards note this in the variant's `what`.
