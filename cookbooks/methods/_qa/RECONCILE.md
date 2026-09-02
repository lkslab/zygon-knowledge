# Pass 1.5 — reconciling the slug list against the evidence

Decisions taken after `pivot_evidence.py` inverted 100 per-paper records into
`EVIDENCE.yaml` (810 paper x method claims). This is the gate that stopped the book
growing to one card per unmatched name. Recorded because the card `prevalence.basis`
fields point here.

## The regex screen was wrong, and that is the interesting part

`SWEEP.csv` (regex screen) and the hand-coded pass-1 read disagree badly, always in
the same direction — the screen **undercounts**:

| method | sweep hits | hand-coded | why |
|---|---:|---:|---|
| foresight-and-planning-horizons | 38 | **81** | almost every paper picks overnight-vs-myopic, most without using either word |
| carbon-constraints-and-pricing | 49 | **67** | a CO2 cap is stated as a scenario name ("1.5°C"), not as "CO2 cap" |
| shadow-prices-and-marginal-values | 42 | **45** | close — this vocabulary is standardised |
| mga-near-optimal-space | 12 | **6** | the one that **overcounts**: "near-optimal" is used loosely in related work |
| model-validation-and-backtesting | 0 | **4** | the regex was simply broken (see below) |

Consequence for the cards: `prevalence.papers` is the hand-coded number, and
`prevalence.sweep_hits` records the screen so the disagreement stays visible instead
of being silently resolved. Where a card's two numbers differ by more than ~30%, the
`basis` field says which direction and why.

## Slug list: 34 -> 35

**Added one.** `model-validation-and-backtesting` (family
`tooling-and-reproducibility`). Four papers make validation their method and were
forced to log it under `unmatched_methods` because no slug existed:

- `2026_Karkossa_optimal-dispatch-models-recreate-reality.pdf` — hindcast of dispatch
  against observed generation, sMAPE scoring
- `2024_Gallego-Castillo_PyPSA-Spain-extension-PyPSA-Eur_ESR.pdf` — quantile-to-quantile
  bias correction of renewable profiles against observed generation
- `2025_Franken_Risk-Reward-National-to-Zonal-Electricity-Market-GB.pdf` — data-driven
  daily line-capacity calibration
- `2025_Xiong_Modelling-High-Voltage-Grid-Open-Data_NatSciData.pdf` — grid model
  validated against reported statistics

This is also the one case where the pass-0 regex was outright defective: the original
bank had no validation pattern at all in `SLUGS.yaml`, and the exploratory sweep's
`validation/backtest` key returned 0 papers, which read as "nobody does this" when the
truth was "the screen cannot see it". The replacement regex is in `SLUGS.yaml`.
**The pass-2 author for this card is the one exception to the no-PDFs rule** — the
evidence lives in `unmatched_methods`, not in a method slice, so that agent re-reads
those four papers' cached text.

**Dropped none.** Two slugs came in at 1 paper and were kept rather than folded,
because each absorbs unmatched entries that are the same method under another name:

- `stochastic-and-robust-optimisation` (1 -> 3): absorbs `regret-analysis`
  (Xiong PCI) and `arimax scenario generation` (Welfonder) as variants. Two-stage
  recourse is different mathematics from re-running a deterministic model over
  samples, so folding it into `sensitivity-and-uncertainty-sweeps` would have hidden
  the distinction the interview most needs to make.
- `soft-linking-with-iam` (1 -> 3): absorbs `endogenous-material-factor-linking`
  (Burghardt) and `bottom-up demand scenario construction (leap/hypat)`
  (Duque-Perez). The method is the coupling protocol, not the identity of the
  partner model.

**Created no other new slugs.** Only two unmatched names recur across papers, and
both are variants of an existing card rather than methods in their own right:

- *flow-based market coupling* (JRC 2024, Thomassen 2025) -> a variant of
  `zonal-nodal-and-redispatch`
- *market-potential method* (Parzen 2021, 2023) -> a variant of
  `storage-sizing-and-duration`, and its `critiques` role there

The remaining 42 unmatched names appear once each. They are study-specific
constructions (depth-dependent offshore cost curves, EOF+k-means weather regimes,
Chebyshev-centre robust design, flow tracing, PCA of flow patterns), correctly kept
out of the vocabulary: a card per one-off is a card nobody retrieves. Pass-2 authors
should mine them for `variants` and `procedure` detail — they are in
`EVIDENCE.yaml:unmatched_methods` keyed by name.

## Mention-only suspects: advisory, not authoritative

`pivot_evidence.py` flagged 30 claims whose text admits the paper did not exercise the
method. Reviewing them, the detector **over-triggers**: most are legitimate uses
carrying a caveat ("CO2 cap applied to all sectors jointly, *losses not modelled*"),
and the phrase match lands on the caveat. Genuine mention-only cases are few:

- `unit-commitment-and-ramping` / Hoersch 2017 cycle-flows — UC named as motivation, never run
- `zonal-nodal-and-redispatch` / Hoersch 2017 cycle-flows — nodal throughout, no comparison
- `spatial-clustering-and-resolution` / Hoersch 2018 PyPSA-Eur — kernel k-means used for
  topology validation, not network reduction (belongs to the new validation card)

Pass-2 authors judge each flagged claim in their own slice and exclude it from
`prevalence` if it is a mention. The flag exists so the judgement is made
deliberately rather than by accident; it is not a delete list.
