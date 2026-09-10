# Baseline prebuild — how far to pre-run the models

The template in `models/<model>` must be a **settled workflow**: under its
reference config, `snakemake -n` proposes ZERO jobs. Settledness is what makes
`referee/check_dag.py` an oracle (post-apply dry-run diff = exactly the
subgraph a bundle invalidates) and what makes eval execution cheap (only the
invalidated delta recomputes). An unsettled baseline swallows the signal —
verified empirically: on a 92-jobs-pending tree, a config change diffs to
nothing because its downstream is already pending.

## Principles

- **One reference configuration per model, plus country variants**, each
  small enough to solve in minutes, stored in
  `fixtures/recipes/baseline-<model>/` (`config.yaml` = the default — GB for
  eur, Mexico for earth; `config.<cc>.yaml` = variants: cr/ng/gh on earth,
  de/fr on eur — all prebuilt into the same template and simultaneously
  settled. Ghana added 2026-07-30 (fully cached in the authoring repo:
  ghana pbf, gadm41_GHA, global UNSD/EDGAR, africa cutout — 42 jobs, ~11
  min, Optimal, zero downloads; EDGAR pin 25.6386 kt). France added
  2026-07-30 (Europe cutout covers it, JRC-IDEES FR present, hotmaps FR
  carries all sectors incl. Non-ferrous metals — the PT crash cannot fire). Portugal was attempted and dropped 2026-07-30:
  single-small-country eur baselines can crash the exogenous industry chain
  — `build_industrial_energy_demand_per_node_today` indexes hotmaps-derived
  sector columns unconditionally, and PT alone has no 'Non-ferrous metals'
  sites; a companion country would fix it, GB+IE-style, at the cost of an
  Iberia-sized system). `harness provision|oracle --baseline config.<cc>.yaml` selects a
  variant: BOTH models take it as the per-invocation `--configfile`
  (since 2026-08-01; eur previously baked it into the clone's installed
  config, which reordered nested dict keys vs snakemake's own merge and
  fired spurious params triggers — France incident, issue #3 in
  runs/issues/eur-baselines-20260731.md). Evals that
  change config get new output filenames and rebuild only their delta —
  that is the design working, not a problem.
- **Resolution variants (2026-07-31)**: alongside the country family, a
  minimal-spatial high-temporal-resolution family for questions that live
  in time rather than space: eur `config.de1.yaml` (germany-2n: 2
  clusters — clusters=1 crashes add_heat's `.squeeze()` on the
  single-node DataFrame, the PT/GB-alone partial-scope class — 3-hourly
  full year, ~2M-row LP) and earth `config.{mx,cr,ng,gh}1.yaml`
  (<country>1: full 2013 year hourly, power-only, at the grid's MINIMAL
  cluster count — CR 1, NG/GH 2, MX 4; earth's cluster_network floors at
  the number of disconnected OSM grid components per country). Same install/settle ceremony, same
  templates. One node = no transmission/siting and copper-plate-optimistic
  storage numbers — the interview method says this to the user (CONTEXT.md
  "Resolution variants"). EUR OVERLAY RULE learned from the France
  incident: variant overlays should override only keys that already exist
  in the installed config — NEW nested keys reorder the baked dict vs the
  configfile merge path, and snakemake's params provenance hashes dict
  repr(), firing spurious "params changed" on whole-dict-params rules
  (fixed 2026-08-01: eur variants moved to configfile-style invocation
  like earth; the rule is now advisory hygiene, not load-bearing).
- **Prebuild = pure compute, zero download.** All retrieval-stage inputs are
  copied from existing local installs (hydrate-style, mtime-preserving), never
  re-fetched.
- **`.snakemake/` records are part of the baseline.** The `params`
  rerun-trigger is the ONLY way snakemake sees config changes (they touch no
  file mtimes); it compares against these records. Ship `metadata/`, `params/`,
  `code/`, `input/`, `iocache/` — not `conda/`, `log/`, `locks/`, `storage/`.
- **No path-dependent params.** Any rule param that embeds an absolute repo
  path (pypsa-eur: `custom_extra_functionality`, resolved via
  `os.path.dirname(workflow.snakefile)`) re-evaluates differently in every
  runspace clone → "params changed" → permanently unsettled. Disable such
  params in the reference config; the settle check below only catches this
  if run in a CLONE, never in the template itself (verified 2026-07-23: the
  template settled while clones re-proposed the solve).
- After building: verify `snakemake -n` proposes zero jobs (default
  rerun-triggers, not just mtime) **in a fresh clone, not in the template**,
  then `chmod -R a-w` the template.
- **The freeze has one planned exception in clones** (discovered 2026-07-26
  when the oracle first re-planned over a clone): snakemake refuses to even
  dry-run over a write-protected existing output (ProtectedOutputException),
  and hardlinks share inode modes, so the run-scoped output subtrees
  (`resources/<run>`, `results/<run>` — the profile's `writable_subtrees`)
  are REAL-copied (`cp -a`, mtime-preserving, then `u+w`) into every clone
  instead of hardlinked. Costs ~0.8G/clone on eur; everything else stays
  hardlinked and frozen, and clone DIRECTORIES get `chmod u+w` (new inodes —
  the template keeps its modes).

## Reference configuration (proposal)

**pypsa-eur** — mirrors the setup already proven tractable in the enderpearl
work (FOCUS-GB, 168H, minutes-scale solve):

| knob | value | why |
|---|---|---|
| countries | `[GB]` | single synchronous area, existing FOCUS-GB experience |
| clusters | 5 | enough spatial structure for siting questions, tiny LP |
| weather year | one (2013 cutout slice) | cutout exists locally; no download |
| temporal | `168H` sector-opts wildcard | proven: solve in minutes, non-degenerate |
| horizon | overnight 2050, sector-coupled | most topic cards need sectors |
| solver | gurobi (licensed) or highs | either solves this size in minutes |

**pypsa-earth** — **Mexico**, adopting the proven cookbook-validation config
(`fixtures/recipes/baseline-pypsa-earth/config.yaml`, from the earth
checkout's `configs/scenarios/validation.mexico.yaml`): 4 clusters, one week
of 2013, power net solved + sector prenetwork, deliberately RAM-light.
Advantage over eur: the earth checkout is CLEAN at exactly the submodule
commit (`8435f4c8`), so its already-computed `resources/mexico-*` and
`results/mexico-*` were built by unmodified template code and are copied in
directly — earth arrives at T1–T4 largely prebuilt, needing only a settle
check. Invocation note: earth applies scenario configs via
`snakemake --configfile <config>`, and needs its own env (snakemake 7.x from
`earth/pypsa-earth/.pixi`), not the eur env.

## Status (2026-07-23)

- **pypsa-eur: BASELINE DONE — settled and frozen (2026-07-23 evening).**
  T0: cutout (6.2G), `data/` (1.5G), http-storage cache (661M) copied; zero
  retrieval jobs verified. T1–T4 built in ~30 min wall-clock on the patched
  fork (`849c8858`): GB+IE, 5 clusters, 168H, overnight 2050, industry +
  endogenous heat ON. Solved at €46.1bn objective (150 buses, 427 links, 53
  snapshots). Three defects found and fixed along the way: GB-only crashes
  the IDEES chain (scope → GB+IE); two partial-scope bugs in the fork's
  industry scripts (→ commit `849c8858`); `custom_extra_functionality`
  resolves to an absolute path in solve params (→ disabled; see principle
  above). KNOWN GAP: GB industrial demand ≈ zero in the data chain — GB
  industry is effectively unmodelled until the fork carries a real GB source
  (DESNZ). Settle check: fresh clone, default triggers → "Nothing to be
  done". Template `chmod -R a-w`; fixtures linked
  (`fixtures/networks/pypsa-eur-{prepared,solved}.nc`).
- **pypsa-earth: BASELINE DONE — settled and frozen.** NA cutout (28G),
  `data/` (36G), shared resource files, `.snakemake/` records, and the Mexico
  `resources/`+`results/` copied in. Settle check initially proposed 47 jobs
  (9 root rules "code changed" — their provenance records were absent, and
  absence fires the trigger; the scripts had upstream robustness/endpoint
  fixes after the runs). Resolved with `snakemake --touch` on the two final
  targets (full DAG, dependency order — refreshes mtimes consistently AND
  writes fresh provenance; metadata backup in
  `fixtures/recipes/baseline-pypsa-earth/`). Verified: fresh clone, default
  rerun-triggers → "Nothing to be done". Template `chmod -R a-w`; fixtures
  linked (`fixtures/networks/pypsa-earth-{solved,prepared}.nc`). Honest
  caveat: provenance now claims current code built everything; for the 9
  retrieval/prep rules the outputs actually predate download-mechanics fixes
  (same datasets, changed fetch code) — re-pull on good WLAN if that ever
  matters.

## How far to run — the tiers

Build through the FULL chain for the reference config, in this order. Stop
points are per-tier for staging the work, but the end state is all five.

- **T0 — retrieval inputs** (copy, not compute): databundle, cutout, costs,
  powerplants, JRC/eurostat data. Source: the existing 43G
  `enderpearl/pypsa-eur` checkout / `res/v1` install.
- **T1 — geodata + profiles**: shapes, base network, availability matrices,
  renewable profiles. The compute-heavy, config-stable middle.
- **T2 — electricity chain**: `add_electricity` → clustered network at the
  reference cluster count.
- **T3 — sector resources**: the long tail (heat demand, industry, biomass,
  gas network, population layouts, …) — the ~90 rules seen pending on an
  unbuilt tree. Slow in aggregate; almost all config-stable at fixed scope.
- **T4 — the heads** (these double as the referee fixtures): the prepared
  pre-solve sector network → symlink as `fixtures/networks/<model>-prepared.nc`,
  and ONE solved network → `fixtures/networks/<model>-solved.nc`.

Do NOT prebuild: alternative configs, extra planning horizons, myopic
pathways, higher resolutions. One settled line per model; evals pay for their
own deltas — and that cost is itself the signal check_dag measures.

## Prerequisite: alignment (currently broken three ways)

Discovered while smoke-testing the referee:

1. **Submodule vs cookbook anchor — RESOLVED, then MOVED (2026-07-23)**: the
   anchor is now fork commit `849c8858` (branch `endogenous-industry-heat`):
   `3e32e3c6` plus the partial-scope industry fixes authored during the
   baseline build (skip zero-production endogenised sectors; mean-ratio
   fallback for non-IDEES countries). The enderpearl checkout was
   fast-forwarded to the same commit, every cookbook `version_anchor`
   re-anchored, and all four `_qa` checkers re-run green (110/110 + 36/36
   recipes, 100/100 topics, registry ok). NOTE: the zygon submodule pointer
   needs committing, and the fork branch exists in no public remote — a
   fresh clone cannot fetch it until pushed somewhere reachable.
2. **Env vs model — RESOLVED (2026-07-23)**: `python-dotenv` + `ruamel.yaml`
   pip-installed into the reused pixi env (via ensurepip); Snakefile parses
   cleanly; the `referee/_shims/` workaround is deleted.
3. **Reference config vs prebuilt state — OPEN**: the enderpearl checkout's
   `config/config.yaml` points at outputs that are not what its resources/
   contain — that mismatch is what an eval baseline must never have. The
   settle check above is the guard.
