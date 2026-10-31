# energy_brockhaus — global energy policy reference

A longitudinal, cross-source database of **assets, targets, subsidies and
regulation** for the world's energy systems. It exists so the interviewing agent
can answer *"what applies to country C, in year Y, for technology T?"* without
trawling primary sources mid-interview — and, just as important, can tell a gap
in the world ("this country has no 2050 target") from a gap in us ("nobody has
collected it yet").

It is the policy counterpart to `cookbooks/<model>/data_quality/`. That says how
good the *model's input data* is for a country; this says what the country has
actually committed to.

> **Query through `tools/registry.py`, not by reading the CSVs.** The tool
> resolves technology aliases, brackets milestone years, ranks scenarios,
> attaches the PyPSA carrier, and reports coverage. Raw grep silently misses
> rows (`PV` vs `solar`) and is the unreliable path.

```bash
python3 tools/registry.py pack  --country NG --year 2030   # full bundle, JSON
python3 tools/registry.py query --country DE --type targets --tech offshore
python3 _qa/check_registry.py                              # the mechanical oracle
```

Stdlib only — no pandas, no env activation. Runs anywhere `python3` does.

## The three query axes

- **`country`** — ISO-2 (`DE`, `NG`, …), or a bloc code from `blocs.csv`.
  A query for a member state also pulls the rows of every bloc it belongs to,
  tagged `_via` so an inherited row is never mistaken for a national one.
  Pass `--no-blocs` to suppress.
- **`year`** — meaning is per-table (commissioning / target / in-force). Targets
  exist for milestone years; an off-milestone query returns the **bracketing**
  rows flagged `nearest`, never an empty result.
- **`technology`** — a canonical token from `technology_taxonomy.csv`; aliases
  (`pv`, `offshore`, `ccgt`) resolve automatically. Every row carries
  `model_carrier`, so a target maps straight onto a PyPSA carrier.

## Tables

| file | rows | grain | `year` means |
|---|---|---|---|
| `targets.csv` | 5,547 | one target value | target year |
| `assets.csv` | 2,055 | one physical asset | commissioning |
| `regulation.csv` | 923 | one law / mandate / ban | effective |
| `subsidies.csv` | 757 | one support instrument | in force |

Supporting: `technology_taxonomy.csv` (35 tokens ↔ carrier ↔ aliases),
`blocs.csv` (120 memberships across 9 blocs), `sources.csv` (3,643 tiered source
documents), `coverage.csv` (**generated** — see below).

`targets.csv` separates three things that used to be crammed into one `unit`
column. See `SCHEMA.md`; the short version is `unit` is a closed 22-token
vocabulary of pure dimension, `basis` is the denominator that makes two
percentages comparable, and `scope_note` is prose that is never grouped on.

## Coverage is generated, and it decays

`coverage.csv` is regenerated from the data by `tools/build_coverage.py`; hand
edits are rejected by `_qa/check_registry.py`. Every (country, table) cell in the
223-country universe gets a row, **including the empty ones**, so `missing` is a
statement rather than a fallthrough. A cell whose newest `retrieved` is more than
24 months old is demoted one rung and says so — coverage rots on its own rather
than staying frozen at whatever it was on import day.

Verdicts: `complete` / `partial` / `seed` / `missing`.

## Honest limits

- **Depth is uneven and the reason is one bulk import.** 4,511 of 5,547 target
  rows come from Ember's NECP compilation, which covers EU27 only. So a European
  country looks deep in *scenario projections* (`WEM`/`WAM`) while the rest of
  the world is thinner but made of *commitments* (`legislated`, `ndc`).
  `SCEN_RANK` ranks commitments above projections, so a query resolves correctly
  either way — but a raw row count will mislead you.
- **78 countries sit below the per-table floor**, most short on `targets`
  specifically. `python3 tools/worklist.py status` is the ranked to-do list.
  The first fill batch took 8 of them (SS, IL, VE, MW, ML, GE, ET, BO) and
  brought 7 to the floor; see below for what that cost in review.
- **A further 81 countries have no rows at all** — mostly small states and
  territories. Breadth, not depth; deliberately after the floor work.
- **138 target groups share a queryable key but differ only in `notes`** — an
  aggregate and its components from the NECP import that the schema cannot
  separate. Surfaced as a WARN, not hidden.
- **64 rows were quarantined** in `policy/_work/contradictory_targets.csv` until
  the 2026-10 trim (git history): the import recorded two values under
  byte-identical provenance and nothing can adjudicate them. Recoverable by
  re-importing Ember with its `FUEL_LOWER` column.
- **9,235 of 9,282 rows share one `retrieved` date** (2026-06-28, the bulk
  import); the 47 rows from the first fill batch carry a real date. Honest, not
  a bug — but staleness only starts discriminating as more research lands.

## Filling: research agents fabricate, so nothing lands unaudited

The fill loop is deliberately two-stage, and the second stage is not optional.
Research agents are **read-only** — they emit a bundle JSON to `_work/bundles/`
and never touch a table — and an adversarial auditor tries to *refute* every row
against its source before a serial integrator lands it.

This is not defensive theatre. The first batch's very first country produced
6 rows of which 2 were fabricated: a hydro capacity the agent had summed itself
from a table of individual stations and recorded as though the document stated
it, and an emissions target with a base year appearing nowhere in the source
plus the more flattering of two conflicting percentages. Nothing reached the
tables.

The fix was a prompt rule, and it worked: **every row's `notes` must open with
the verbatim sentence from the source containing the figure**, or the row is
deleted. Re-running 8 countries then gave 6 clean, and the 2 flagged failed on
overstated `confidence` and a wrong page locator rather than invented numbers.
Those were corrected — values untouched, confidence capped, conflicts disclosed
— and landed. All 47 rows carry a quote that literally contains their value.

Treat the mechanical checker as necessary and not sufficient: it cannot see
fabrication. Spot-audit real rows by hand every batch.

## What changed from the enderpearl registry

| | before | after |
|---|---|---|
| distinct `targets.unit` strings | 155 | 22 (closed vocabulary) |
| rows with free-text units | 114 | 0 |
| tier-3 sources backing `confidence: high` | 1,809 | 0 |
| `coverage.csv` rows | 15 (hand-maintained) | 2,676 (generated) |
| countries falling through to `missing` | ~138 | 0 |
| EU rows leaking into non-member packs | all 143 countries | members only |
| self-contradicting target rows | 64 | 0 (quarantined) |
| tools requiring pandas | 5 | 0 |
| mechanical checks | 4 | 10 |

`tools/` keeps every migration script that produced this state, so each step is
auditable rather than a claim.

See `MAINTAINER.md` for the standing task and the provenance rules,
`SCHEMA.md` for the normative column definitions.
