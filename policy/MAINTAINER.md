# energy_brockhaus — the standing maintenance task

Keep the four tables accurate, well-sourced, and honest about their own gaps.
The consumer is the interviewing agent, via `tools/registry.py`.

**Quality and provenance over volume. An unsourced row is worse than a missing
one, and a contradictory row is worse than both** — a missing row makes the
agent say "not collected"; a bad row makes it say something false with
confidence.

## Hard rules (the checker enforces all of these)

1. **`source`, `source_url`, `retrieved` are mandatory.**
   `integrate_research.py` *rejects* a row without them — it does not fill them
   in. `retrieved` is when *you actually read the source*; it is never
   auto-stamped. A hardcoded `RETRIEVED` constant is why all 9,235 legacy rows
   share one date and staleness detection was dead on arrival.
2. **`source_url` must be registered in `sources.csv`.** Run
   `tools/build_sources.py` after any import.
3. **Tier 3 caps confidence at `med`.** Press, wiki and trade blogs cannot back
   a `high` claim. If a number matters, find the ministry document.
4. **`technology` must exist in the taxonomy first.** Add the token, with its
   `model_carrier`, before importing rows that use it.
5. **Units come from the closed vocabulary**, and the denominator goes in
   `basis`, not into the unit string. See `SCHEMA.md`. If a quantity genuinely
   does not fit — a credit instrument, a monetary flow, a count of solar kits —
   it is not a numeric target: put it in `regulation.csv` as prose.
6. **Unique, stable `record_id`.** Corrections overwrite and bump
   `last_updated`; never fork a near-duplicate.
7. **Never invent a value.** If the floor cannot be met from tier ≤2 sources,
   leave the cell short and write the reason into `coverage.csv:known_gaps`.
   The floor is a floor for effort, not a quota to satisfy.

## Each run

```bash
python3 tools/worklist.py status            # 1. the ranked to-do list
python3 tools/worklist.py next --take 8     # 2. claim a batch
# 3. research each country against the source tiers below
python3 tools/integrate_research.py _work/bundles/XX.json --dry-run   # 4. gate
python3 tools/integrate_research.py _work/bundles/XX.json             # 5. land
python3 tools/build_sources.py              # 6. refresh the provenance index
python3 _qa/check_registry.py               # 7. must exit 0
python3 tools/build_coverage.py             # 8. regenerate coverage
python3 _qa/check_registry.py               # 9. must still exit 0
```

Steps 4–9 must run **serially**. `integrate_research.py` and
`build_sources.py` rewrite whole CSVs, so concurrent writers clobber each other.
When filling in parallel, research agents are read-only — they emit bundle JSONs
to `_work/bundles/` and nothing else — and one integrator lands the batch.

**Then spot-audit 5 random new rows by hand.** No mechanical check can see
fabrication. Sampling is the only defence.

## Source tiers

- **Tier 1** — national ministries and gazettes (any `.gov`/`.gouv`/`.gob`/`.go`
  domain), EUR-Lex, UNFCCC.
- **Tier 2** — IEA, IRENA, Ember, Global Energy Monitor, World Bank, ENTSO-E,
  Climate Action Tracker, climate-laws.org, official project/company sites.
- **Tier 3** — press, trade publications, wikis, consultancies. Usable for
  context and for `med` at best; never the sole basis for a `high` number.

**The UNFCCC NDC Registry is the highest-yield single source** for the current
gap. One document per country yields an economy-wide emissions target with
`scenario=ndc`, which satisfies two of the three mandatory `targets` items in
one go — and `ndc` outranks every projection in `SCEN_RANK`, so it is exactly
what the thin countries are missing.

## Known repair jobs

- `_work/contradictory_targets.csv` — 64 rows quarantined because the Ember
  import recorded two values under identical provenance. Re-import Ember
  carrying its `FUEL_LOWER` column and they can come back.
- 138 target groups differ only in `notes` (an aggregate and its components).
  Same root cause; same fix.
- 81 countries have no rows at all. Breadth work, after the floor.
