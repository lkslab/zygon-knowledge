# energy_brockhaus — schema

`schema_version: 2`

Normative column definitions. Not in `contracts/`: that directory is the API
between this repo and the front-end, and is treated as a breaking-change
surface. This schema has no external consumer yet and was just broken (v1 → v2),
so freezing it now would be premature. Promote it once the fill campaign has
exercised the vocabulary and it stops moving.

## Shared spine

Every row in the four fact tables carries:

| column | meaning |
|---|---|
| `record_id` | unique, stable. Corrections overwrite in place and bump `last_updated`; never fork a duplicate. |
| `country` | ISO-2, or a bloc code from `blocs.csv`. |
| `technology` | a canonical token from `technology_taxonomy.csv`. |
| `model_carrier` | denormalized from the taxonomy so a consumer skips a join. |
| `source`, `source_url`, `retrieved` | mandatory. A row without them is rejected at integration, not warned about. |
| `confidence` | `high` / `med` / `low`. Capped by source tier — see below. |
| `last_updated`, `notes` | |

`necp_fuel_code` was removed in v2. It was a pure function of `technology`
(verified: 0 of 9,299 rows disagreed with the taxonomy), so carrying it on every
row was redundancy that could only drift. It remains in
`technology_taxonomy.csv`; join there if you need it.

## targets.csv — the v2 change

v1 had one `unit` column doing three jobs, and 155 distinct strings in it —
114 rows carrying free text like `"GW WtE incineration (qualitative
steady-development goal)"`. That was not merely untidy: `registry.py`'s
`select_targets()` groups by `(country, technology, metric, unit, …)`, so a
unique unit string put a row in a group of one, and scenario-preference and
year-bracketing silently did nothing for it.

v2 splits it into three columns with distinct contracts:

| column | contract |
|---|---|
| **`unit`** | Closed vocabulary, **pure physical dimension only**. The checker FAILs on anything outside it. 22 tokens: `GW MW GWh MWh TWh PJ TWh/yr PJ/yr MtCO2eq MtCO2 MtCO2/yr pct Mt/yr kt/yr t/yr bcm/yr Smc/h Ggal/yr kb/d bbl/d count ratio`. Note `pct`, not `%`. |
| **`basis`** | Closed vocabulary, **the denominator**. What makes two percentages comparable or not. `""` for absolute units, and `""` for a percentage whose base the source never stated — which is honest, not a gap to guess at. 17 tokens, e.g. `electricity_generation`, `gross_final_energy`, `population`, `baseline_year`. |
| **`scope_note`** | Free text, **non-load-bearing by construction**. Never in a grouping key, never parsed. Holds the residue (`"max ceiling"`, `"Offshore"`, `"expected"`) that used to be welded into `unit` and fragment the groups. |

Both vocabularies are defined once, in `tools/unit_map.py`, and imported by the
migration and the checker alike.

`metric=emissions` stays a single metric; `(MtCO2eq, "")` and `(pct,
baseline_year)` disambiguate absolute from relative. Forking it into
`emissions_abs`/`emissions_rel` would have broken every query by name.

### Grouping keys — two of them, on purpose

- `select_targets()` groups on `(country, technology, metric, unit, basis)`.
  `scope_note` is excluded: grouping on prose would re-fragment groups exactly
  the way free-text units did.
- `check_registry.py:duplicate-fact` keys on all of the above **plus `notes`**.
  Contradiction detection wants maximum specificity: two rows with identical
  provenance and different values are corrupt (FAIL), while two rows differing
  in `notes` are distinct facts the schema under-distinguishes (WARN).

## blocs.csv

`bloc, member, bloc_name, kind, notes` — long format, so a country can belong to
several. `member = "*"` means every country.

`kind` decides default inclusion in a member's query:

| kind | unioned by default | example |
|---|---|---|
| `supranational_binding` | yes | EU27 |
| `intergovernmental` | yes | AFU, ASEAN, GCC, MERCOSUR, ECOWAS |
| `global_instrument` | yes | UNFCCC (Paris/NDC) |
| `global_sectoral` | **no**, opt in with `--bloc` | IMO, ICAO |

A bloc code must not be a valid ISO-2 country code; `build_blocs.py` refuses to
emit a file that violates this. The African Union is `AFU`, not `AU` — `AU` is
Australia, and using it made every African country inherit Australian rows.

## Scenario ranking

Lower wins when several scenarios describe one target (override with
`--scenario`):

| rank | scenarios | rationale |
|---|---|---|
| 0 | `legislated`, `binding` | domestic law |
| 1 | `adopted`, `ndc` | an NDC is formally communicated but is not domestic law |
| 2 | `announced`, `planned`, `lts` | political commitments |
| 3–5 | `wam`, `wem`, `projection` | Ember NECP scenario trajectories |
| 6 | `proposed`, `indicative` | |

Conflicting values are **kept, not overwritten**, so the disagreement stays
visible; the tool only decides which surfaces by default.

## Source tiers and the confidence ceiling

`sources.csv` auto-tiers by domain (`tools/build_sources.py`):

- **tier 1** — government, legislator, official gazette. Matched by a generic
  pattern (`.gov`, `.gov.xx`, `.gouv`, `.gob`, `.go`, `.govt`, `.gv`) so any
  national ministry qualifies without a per-country allowlist.
- **tier 2** — primary data providers and authoritative compilers: IEA, IRENA,
  Ember, Global Energy Monitor, World Bank, UNFCCC, climate-laws.org.
- **tier 3** — everything else: press, trade, wiki, consultancy.

**A tier-3 source may not back `confidence: high`.** Enforced by the checker.
The rule is *at most `med`* rather than the stricter *`low` only*: 3,187 of
9,235 rows cite tier-3 sources and most are competent trade reporting of a real
project, so blanket-demoting them to `low` would misrepresent the registry more
than it would protect a reader.

## coverage.csv — generated

Regenerate with `tools/build_coverage.py`. The verdict rule lives in
`_qa/check_registry.py:derive_coverage` and is imported by the generator, so the
file and the check that guards it cannot drift.

```
missing  : row_count == 0
seed     : row_count < FLOOR[table]
partial  : row_count >= FLOOR and (best_tier == 3 or no confidence=high row)
complete : row_count >= FLOOR and best_tier <= 2 and >=1 confidence=high
           and (targets only) a 2028-2032 row and a 2040-2050 row
```

Then a **recency demotion**: newest `retrieved` older than 24 months drops the
cell one rung and writes `stale: newest retrieved YYYY-MM` into `known_gaps`.

`FLOOR = {targets: 8, assets: 8, subsidies: 3, regulation: 4}`. This is a floor
for *effort*, never a quota: if it cannot be met from tier ≤2 sources, leave the
cell short and write why into `known_gaps`.

`technology_group = "*"` marks the cell-level roll-up. Not `"aggregate"` — that
is a real technology group in the taxonomy, and reusing the word made group rows
silently shadow the roll-up.
