# GAPS — fields a pass-2 author could not ground

Append one line per gap: `slug` / field / what would be needed. Do not pad a card to
avoid writing here; an honest short field plus a line here is the correct outcome.

- `linearised-optimal-power-flow` / registry (both models) — neither
  `cookbooks/pypsa-eur/topics/FUNCTIONALITY.yaml` nor the pypsa-earth one has an id for
  the LOPF FORMULATION itself (cycle/Kirchhoff vs angle vs PTDF). The card had to hang
  it on `pypsa_primitive` instead. Two registry entries are missing: a `working` id for
  "linearised power flow (Kirchhoff cycle KVL)" noting it is built unconditionally by
  pypsa with no config surface, and — for pypsa-earth only — a `dead-key` id for
  `solving.options.formulation`, whose value never reaches `n.optimize` and for which
  pypsa 0.30.3 has no receiving argument.
- `linearised-optimal-power-flow` / registry (pypsa-earth) — `transmission-losses` is
  absent from earth's registry entirely. That is correct as "no surface exists", but the
  ladder needs it recorded as absent-with-a-nearby-primitive rather than unlisted, since
  the pypsa function eur uses is the same one and the wiring gap is ~2 lines.
- `linearised-optimal-power-flow` / procedure step 8 (ex-post AC validation) — no
  handle in either model, and only one paper in the corpus (Neumann 2022) performed it.
  A referee check for "linear vs AC line loading divergence" would need a fixture
  network with meshed AC branches and a reference AC solution; neither exists yet.
- `foresight-and-planning-horizons` / registry (pypsa-earth) — earth's
  `cookbooks/pypsa-earth/topics/FUNCTIONALITY.yaml` has NO `overnight-foresight` id,
  although `foresight: overnight` is the shipped default and the Snakefile branches on it
  to define `rule solve_sector_network`. The card had to assert the mode from the grep
  alone. Needs a `working` id mirroring eur's, with surface
  `foresight: overnight (default); scenario.planning_horizons as a COST-year selector`
  (earth's own config comment says the key means the cost year under overnight, which eur's
  does not) and consumer `Snakefile:solve_sector_network`.
- `foresight-and-planning-horizons` / registry (pypsa-earth) — no `co2-budget-pathway` id,
  yet `co2_budget.{enable,override_co2opt,co2base_value,year}` exists in
  `config.default.yaml` with a live consumer at
  `scripts/prepare_sector_network.py:add_co2_budget` (called under
  `if co2_budget["enable"]`). That is a real per-horizon emission-share trajectory, off by
  default, and the only policy-pathway surface earth has. Needs a `partial` id (partial
  because there is no per-country historical baseline shipped and no cb-token grammar).
- `foresight-and-planning-horizons` / registry (pypsa-earth) — no `land-use-constraint` id,
  yet `scripts/solve_network.py:add_land_use_constraint` IS called when
  `snakemake.config["foresight"] == "myopic"`, with a cluster-aware branch
  `_add_land_use_constraint_m`. Registry silence here reads as "absent" and understates
  earth's myopic chain. Needs a `partial` id.
- `foresight-and-planning-horizons` / registry (pypsa-earth) — no `perfect-foresight` id is
  CORRECT (there is genuinely no implementation), but the absence should be recorded
  explicitly rather than by omission, because `config.default.yaml`'s comment on
  `planning_horizons` reads "investment years for myopic and perfect" — a dead config
  value that matches no Snakefile branch and yields a DAG with no solve rule rather than an
  error. An `absent` id whose note names that dead promise would stop an agent trusting the
  comment.
- `foresight-and-planning-horizons` / registry (pypsa-eur) — `perfect-foresight` is rated
  `working`, but `scripts/prepare_perfect_foresight.py` logs
  "Running perfect foresight is not properly tested and may not work as expected. Use at
  your own risk!" on import, raises `UserWarning` under pypsa >= 1.0, and
  `scripts/solve_network.py` documents `add_CCL_constraints` as not implemented for it. The
  status is defensible but the note should carry the self-declared caveat and the pypsa
  version ceiling, or `available.verdict: turnkey` over-promises to an interview.
- `foresight-and-planning-horizons` / `verifies` (pypsa-eur, myopic-sequential) — the first
  check is deliberately weak. The real postcondition is "horizon k's network contains
  horizon k-1's surviving capacity as non-extendable, and nothing else", which needs the
  predecessor network in scope. `referee/check_ensemble.py` would have to pass an ORDERED
  ensemble plus the horizon list; the current `over: ensemble` contract does not say
  whether order is guaranteed. Worth settling before backfilling pathway checks.
- `land-eligibility-and-potentials` / registry (pypsa-earth) — three ids that exist for
  pypsa-eur are missing from earth's registry entirely rather than recorded as absent:
  `land-use-constraint`, `solar-potential-constraint` and `max-growth-limits`. The card
  had to state the gap in prose. All three matter here: without vintage subtraction from
  `p_nom_max`, an earth brownfield run can build on land its existing fleet already
  occupies (earth sets `estimate_renewable_capacities.p_nom_min: 1` as a floor but never
  decrements the ceiling), and there is no generic shared-land budget for any pair of
  land-competing technologies.
- `land-eligibility-and-potentials` / registry (pypsa-earth) — `renewable.csp.copernicus.
  distancing_codes` and `distance_to_codes` are DEAD KEYS: they appear in
  `config.default.yaml` and `configs/scenarios/config.GH.yaml` but no `.py`/`.smk`/
  `Snakefile` reads them (`build_renewable_profiles.py` only consumes `distance` and
  `distance_grid_codes`). This deserves a `dead-key` registry entry — a user setting a
  CSP setback there gets a successful run with no setback applied.
- `land-eligibility-and-potentials` / variants `offshore-depth-banded-and-shipping`,
  `profile-bias-correction` — evidence is thin on the QUANTITATIVE side of the two
  extensions the corpus documents but neither model implements. Glaum 2023's
  depth-dependent capital cost (Danish Energy Agency model over depth, rotor diameter,
  hub height, specific power, farm size) and Glaum 2024's piecewise wake-loss schedule
  (9%/21%/32%) are recorded from pass 1's procedure_notes only; the functional forms and
  breakpoints would need the PDFs to author a real `assembly` step. Same for
  Gallego-Castillo's quantile-to-quantile mapping — pass 1 records that it is
  quantile-to-quantile and against what, but not the binning or the fitting period.
- `land-eligibility-and-potentials` / `verifies` — the two most valuable checks for this
  method are cross-artefact, not over a network: "the availability matrix is non-empty for
  every region" and "the eligible fraction per country is within a plausible band" (e.g.
  Gallego-Castillo's audited 64.65% wind / 41.97% PV for Spain). Both need the
  `availability_matrix_{clusters}_{technology}.nc` artefact, which pypsa-eur writes but
  pypsa-earth keeps as an in-memory intermediate. A referee check would need earth's
  `build_renewable_profiles` split before it could run on both models.
- `storage-sizing-and-duration` / registry (both models) — there is NO capability id for
  the central choice this card is about: `electricity.extendable_carriers.{StorageUnit,Store}`
  plus `electricity.max_hours.*`, i.e. fixed-duration versus independent energy/power
  sizing. It is the single most consequential storage config surface in either repo
  (Parzen measures ~10% total system cost between the two forms) and neither registry
  names it. Both need a `working` id — surface
  `electricity.extendable_carriers.{StorageUnit,Store}; electricity.max_hours.<carrier>`,
  consumers `scripts/add_electricity.py:attach_storageunits` /
  `:attach_stores` for eur and `scripts/add_extra_components.py:attach_storageunits` /
  `:attach_stores` for earth. The card had to hang the levers on `battery-charger-ratio`
  and `pypsa_primitive` instead, which understates it.
- `storage-sizing-and-duration` / registry (pypsa-eur) — `battery-charger-ratio` is rated
  `partial` for the right reason (the name filter misses the lfp/vanadium/lair/pair/iron-air
  suite) but the note omits the compounding half: `attach_stores` assigns the discharger
  ZERO capital cost for every `bicharger` technology, so for those carriers discharge power
  is both uncoupled AND free. That is a silent competitive advantage in any
  multi-technology comparison and belongs in the note.
- `storage-sizing-and-duration` / registry (pypsa-eur) — no id covers the fact that the
  TES energy-to-power ratio is a DATA value (`energy to power ratio` column of the
  processed cost table: 22.5 h central water pit, 60.3 h central water tank, 0.15 h
  decentral water tank at this ref), not a config key. `tes-constraints` is rated `working`
  and reads as an L0/L1 surface, but changing a thermal duration is L3. Also worth
  recording that `sector.tes_tau` is present in eur's config as `None` and read by nothing —
  a dead key that looks like the lever and is not.
- `storage-sizing-and-duration` / registry (pypsa-earth) — `battery-charger-ratio` is
  ABSENT from earth's registry although `scripts/solve_network.py:add_battery_constraints`
  exists and is called unconditionally, and earth's link naming does match its filter.
  Registry silence reads as "no such capability" and understates earth. Needs a `working`
  id mirroring eur's.
- `storage-sizing-and-duration` / registry (pypsa-earth) — no `tes-constraints` id, which
  is CORRECT (earth has no energy-to-power or charger-ratio constraint on thermal storage
  at all — `scripts/prepare_sector_network.py:add_heat` builds the store and both links
  fully extendable and uncoupled) but should be recorded as an explicit `absent` id rather
  than by omission, since eur's equivalent is `working` and the asymmetry is load-bearing.
- `storage-sizing-and-duration` / registry (pypsa-earth) — `sector.marginal_cost_storage`
  has no id in either registry. It is a live key here (consumer
  `scripts/prepare_sector_network.py:add_storage`, default 0) and it is the ONLY
  first-class config surface in either repo for the unintended-storage-cycling remedy the
  corpus's one `critiques` paper prescribes (Parzen 2023 uses 0.5 EUR/MWh). In pypsa-eur
  the same name appears only in a `prepare_sector_network.py` docstring and is absent from
  `config.default.yaml` — a documented key that does not exist. Needs a `working` id for
  earth and a `dead-key`/`absent` id for eur.
- `storage-sizing-and-duration` / registry (pypsa-earth) — two defects found by grep that
  no id records, both in `scripts/prepare_sector_network.py:add_hydrogen` under
  `sector.hydrogen.underground_storage` (default false). In the non-custom branch the
  `H2 UHS charger` is wired `bus0=<electricity bus>` instead of the H2 bus, and the
  `H2 UHS discharger` repeats the charger's direction (`bus0=<node>`,
  `bus1=<node> H2 UHS`), so the cavern can be filled from electricity at efficiency 1 and
  can never discharge. Both branches also create UHS buses at ALL nodes while placing
  Stores only at cavern nodes, leaving orphan buses. This deserves a `broken`/`dead-key`
  id — the feature does not error, it silently produces a store that never delivers.
- `storage-sizing-and-duration` / registry (pypsa-earth) — `renewable.hydro.extendable`
  is a dead key for hydro: nothing reads it and
  `scripts/add_electricity.py:attach_hydro` hardcodes `p_nom_extendable=False`. Since the
  key is `true` by default it reads as "reservoir capacity is an investment variable",
  which it is not. Needs recording, most naturally on `hydro-inflow-normalization`.
- `storage-sizing-and-duration` / `variants[].papers` for `exogenous-capacity-placement` —
  the variant is grounded (5 papers), but pass 1's per-paper `variant` field used
  free-text labels that do not reconcile across papers (`fixed-duration`,
  `fixed-duration-ratio`, `fixed-e-to-p-ratio`, `independent-power-energy-sizing`,
  `independent-e-p-sizing`, `co-optimised-energy-power` all appear for what are two
  representations). Assignment to this card's six variant ids was therefore made from each
  paper's `evidence`/`procedure_notes` prose, not from that field. Fine here, but a future
  pass should not trust `EVIDENCE.yaml:variant` as a join key.
- `storage-sizing-and-duration` / `verifies` (both models) — the most valuable check on
  this surface is a LINK-DIRECTION and bus-topology assertion ("every discharger's bus0 is
  the store's bus"), not a presence or count check. `referee/check_network.py` can express
  it as a pandas predicate over `n.links`, but nothing in the fixtures currently contains a
  Store+charger+discharger triple, so the check is authored and unexercised. A fixture with
  one battery and one H2 store built both ways (StorageUnit and Store+Links) would exercise
  every check in this card.
- `spatial-clustering-and-resolution` / registry (pypsa-earth) — `focus-weights` is listed
  as eur-only (`--`) in FUNCTIONALITY.index.md, but earth has a live, grep-verified
  surface: `cluster_options.focus_weights` (plus a top-level `focus_weights` that takes
  precedence), consumed by `scripts/cluster_network.py:distribute_clusters` and read in
  both `cluster_network.py` and `simplify_network.py`. The card had to cite earth's
  `spatial-clustering` id for the heterogeneous-resolution variant instead. Earth's
  registry also has no id for two further live spatial surfaces: `subregion.*`
  (`scripts/_helpers.py:nearest_shape`, a custom/GADM subregion overlay applied at
  simplify_network and/or cluster_network) and the isolated-network thresholds
  `cluster_options.simplify_network.p_threshold_{drop,merge}_isolated`
  (`scripts/simplify_network.py:drop_isolated_networks`), which materially change the
  achievable node count on OSM topologies.
- `spatial-clustering-and-resolution` / registry (both models) — no id covers the
  RESOURCE-vs-NETWORK resolution split, which is the single most load-bearing distinction
  in this card's literature (Frysztacki 2021). eur's lever is
  `renewable.<tech>.resource_classes` (`scripts/build_renewable_profiles.py`), currently
  folded into `renewable-potentials-land-eligibility`; earth's is the surviving
  `scenario.simpl` wildcard, folded into `spatial-clustering`. Both deserve their own ids
  because the interview needs to route "is my resolution biasing the technology mix" to
  them, and because earth's mechanism (profiles built pre-cluster on full-resolution
  regions) and eur's (per-bus capacity-factor bins) are not interchangeable.
- `spatial-clustering-and-resolution` / models[pypsa-eur].boundary
  (decoupled-resource-and-network-resolution) — rated L1 for the half that
  `resource_classes` covers, but the converse (fine network, coarse resource) and true
  two-stage control are L4 and the card asserts that without having run it. eur builds
  profiles on `regions_onshore_base_s_{clusters}`, so reproducing Frysztacki 2021's
  three-case design needs `rule build_renewable_profiles` re-pointed at a
  resolution-independent region file plus wildcard plumbing. Confirming the rung would
  need a `snakemake -n` on a modified rule, i.e. the check_dag oracle, which does not
  exist yet.
- `spatial-clustering-and-resolution` / verifies — every check is written `over: run`
  except one, and they are all bus-count or component-presence assertions. The checks that
  would actually catch this method's characteristic failure are cross-resolution
  (does metric X move by more than Y% between N=37 and N=128?), which needs an ensemble
  referee that compares SOLVED networks at different resolutions. `referee/check_ensemble.py`
  does not exist, and no fixture set spans two resolutions of the same network.
- `spatial-clustering-and-resolution` / inverse-disaggregation — rated L5 in both models
  from the absence of any disaggregation code, which is solid. What is NOT grounded is the
  effort estimate: the card says the three published rules are "post-processing plus a
  small per-cluster LP" based on Frysztacki 2023's description of the objectives, not on
  any implementation. Pass 1's `procedure_notes` give the equations by number but not their
  content, and the PDF is off-limits at pass 2.
- `unit-commitment-and-ramping` / `procedure` step 11 (stochastic UC) and `variants` —
  Welfonder 2024 is the corpus's only stochastic UC and pass 1's `procedure_notes` give
  the shape (MILP with binary x_delta^{t,g}, minimum load, min up/down times, ramping,
  ARIMAX-generated 1000 price/heat-demand realisations) but NOT the two-stage structure:
  whether the binaries are first-stage here-and-now decisions shared across scenarios,
  how many scenarios entered the MILP after reduction, or how the aFRR market was
  represented. Step 11 therefore has `handle: null` and no variant was created for it —
  a `stochastic-uc` variant would need the paper's Eqs. 1-11 and its scenario-reduction
  step. Would need: the PDF, or a pass-1 re-read targeting the two-stage formulation.
- `unit-commitment-and-ramping` / registry (pypsa-earth) — the registry entry
  `unit-commitment` says the surface is only
  `cluster_options.aggregation_strategies.generators.committable`. It misses the actual
  producer route: the UNDECLARED top-level `conventional:` block, read as
  `config.get("conventional", {})` in the Snakefile and applied in
  `scripts/add_electricity.py:attach_conventional_generators` via
  `set(conventional_config[carrier]) & set(n.generators)` — an intersection with the
  Generator dataframe's columns, which reaches `committable`, `p_min_pu`, `min_up_time`,
  `min_down_time`, `start_up_cost`, `shut_down_cost` and `ramp_limit_up/down`. Suggest
  adding an id for "per-carrier conventional generator attribute overrides" with
  status `working` and a note that the key is absent from config.default.yaml (a live
  consumer with no declared surface — the inverse of a dead key). This changes earth's
  UC verdict from effectively-absent to `assemble` at L1.
- `unit-commitment-and-ramping` / registry (pypsa-eur) — the
  `linearized-unit-commitment` entry's surface line claims
  "clustering.aggregation_strategies preserves committable/ramp limits". Verified FALSE
  at 849c885: those three entries are dead config. `clustering_for_n_clusters` passes
  only line and bus strategies to `get_clustering_from_busmap`, and the one consumer of
  `aggregation_strategies["generators"]`, `load_and_aggregate_powerplants`, filters with
  `if k in ppl.columns` — and the powerplant table has no committable/ramp columns
  because `attach_conventional_generators` adds them afterwards. Harmless (add_electricity
  runs after cluster_network) but misleading. Suggest striking that clause from the
  surface line and moving it to the note as a dead-key warning.
- `weather-year-ensembles` / `data_dependencies` (pypsa-eur) — could not enumerate WHICH
  weather years are actually published as pre-built cutouts, which is the single fact
  that decides whether a sequential ensemble is L1 or L3 on eur. CLAUDE.md forbids
  downloads and `models/pypsa-eur/data/cutout/archive/v1.0/` is empty at 849c885, so
  the archive's contents are unobservable locally. What IS verified and enough to make
  the card's crux: `atlite.default_cutout` is `europe-2013-sarah3-era5`, that name is
  NOT a key under `atlite.cutouts` (so `scripts/build_cutout.py`, which does
  `snakemake.params.cutouts[snakemake.wildcards.cutout]`, KeyErrors on it — it is
  download-only), and the one buildable definition `europe-1940-2024-era5` is
  `module: era5` with `prepare_kwargs.sarah_dir: null` and `time: ['2013','2013']`
  despite its name. Needed to close the gap: an index listing of
  `https://data.pypsa.org/workflows/cutout/v1.0/` (a directory listing, not a cutout
  download — cheap, but still a network fetch). Worth doing once and recording in the
  eur data_quality book, since every weather-year study routes through it.
- `weather-year-ensembles` / `prevalence` (method book, cross-cutting) — the sweep regex
  for this slug includes `\bera5\b`, which makes `sweep_hits: 62` against 18 hand-coded
  papers the largest screen over-count in the book. Naming your reanalysis is not
  running an ensemble. Suggest dropping `\bera5\b` and `climate reanalysis` from
  `SLUGS.yaml:weather-year-ensembles.sweep_regex` if the sweep is ever re-run for
  ranking rather than hinting.
- `temporal-aggregation-and-segmentation` / registry (pypsa-eur) — needs a `dead-key`
  entry for `clustering.temporal.sector`. `rules/solve_perfect.smk::prepare_perfect_foresight`
  sets `params.time_resolution=config_provider("clustering", "temporal", "sector")`, but
  `sector` exists in neither `config/config.default.yaml` (only `resolution_elec` and
  `resolution_sector`) nor `config/schema.default.json`, and the shipped
  `config/test/config.perfect.yaml` sets `resolution_sector: 8760h`. So the param resolves
  to None and `scripts/prepare_perfect_foresight.py:apply_time_segmentation_perfect` —
  which is the ONLY per-investment-period aggregation in either model, i.e. the handle for
  Zeyen's typical-days-per-period pattern — is unreachable dead code at 849c885. Its
  guard is additionally `isinstance(segments, (int, float))`, so even if the key were
  added, a string like `'2190seg'` would be silently ignored; it wants a bare integer.
  Suggested entry: id `perfect-foresight-segmentation`, status `dead-key`, surface
  `clustering.temporal.sector (absent from config.default.yaml and schema.default.json)`,
  consumer `scripts/prepare_perfect_foresight.py:apply_time_segmentation_perfect`.
- `temporal-aggregation-and-segmentation` / registry (pypsa-eur) — `temporal-resolution-nh`'s
  note should record that the `drop_leap_day` argument of
  `scripts/prepare_network.py:average_every_nhours` is a NO-OP: the filtered index is
  assigned to a local `sns` and then `set_snapshots` is called on the unfiltered
  `snapshot_weightings.index`. Benign at this ref only because `_helpers.py:get_snapshots`
  already dropped the leap day upstream. The sector path
  (`scripts/time_aggregation.py`) handles it correctly by folding the leap weight onto
  1 March.
- `temporal-aggregation-and-segmentation` / registry (pypsa-earth) — `time-segmentation-tsam`
  is recorded as `working` for earth, which is only half true: `scripts/prepare_network.py`
  has the `^\d+seg$` branch, but `scripts/prepare_sector_network.py` matches `^\d+h$`
  only and contains no occurrence of `seg` at all. A `NNNseg` token in `scenario.sopts`
  is therefore accepted by the wildcard constraint and silently ignored. Suggest
  splitting into `working` (power) plus a note, or downgrading to `partial` with surface
  `scenario.opts NNNseg (power chain only — sopts has no seg branch)`.
- `temporal-aggregation-and-segmentation` / registry (pypsa-earth) — no `drop_leap_day` id.
  The only occurrence in the repo is a COMMENTED-OUT line in the Snakefile, and earth's
  `average_every_nhours` takes no such argument, so a leap-year snapshot window yields
  8784 h and every per-8760 normalisation is off by 24. Worth an `absent` entry, since
  eur has the key and cross-model comparisons will silently disagree.
- `temporal-aggregation-and-segmentation` / `variants.every-nth-snapshot`.papers — empty.
  No corpus paper uses every-nth-snapshot thinning; the variant exists only because
  pypsa-eur ships the `NNsn` surface (`scripts/prepare_sector_network.py:set_temporal_aggregation`)
  and an interview must be able to recognise the token. Closing this would need
  literature outside this corpus (the sampling-vs-averaging bias comparison is a
  time-series-aggregation-methods question, and this corpus contains no
  methods-of-aggregation paper — only Schyska, which studies averaging).
- `temporal-aggregation-and-segmentation` / `procedure` step 6 (representative periods)
  and step 9 (validation) — `handle: null` on both, correctly. Note for whoever writes
  the extraction/metrics book: neither model exposes tsam's `noTypicalPeriods > 1`,
  `clusterMethod='k_medoids'`, `extremePeriodMethod`, `addPeakMax` or `addPeakMin`, all
  of which exist in the installed tsam (0.0.0.dev0, verified by introspecting
  `TimeSeriesAggregation.__init__`). Both call sites hardcode
  `noTypicalPeriods=1, hoursPerPeriod=len(df), segmentation=True`. That means peak
  preservation in BOTH models is whatever the segmentation optimum happens to give, not
  an asserted property — which is the strongest available argument for a referee
  fixture check on extreme-hour survival.
- `brownfield-and-capacity-vintaging` / registry (pypsa-earth) — no `land-use-constraint`
  id, but the code EXISTS: `scripts/solve_network.py:add_land_use_constraint` is called
  from `prepare_network` whenever `foresight == "myopic"`, and `_add_land_use_constraint`
  really does subtract existing p_nom per (bus location, carrier) from the current
  horizon's p_nom_max, clip at zero, and additionally cap p_nom/p_nom_min down when the
  decrement made them infeasible (a guard eur does NOT have). Needs a `partial` entry
  with surface "automatic when foresight: myopic" and consumer
  `scripts/solve_network.py:_add_land_use_constraint`, plus the two defects below. The
  capability is currently invisible to routing, which is worse than it being absent.
- `brownfield-and-capacity-vintaging` / BUG (pypsa-earth) —
  `scripts/solve_network.py:_add_land_use_constraint_m` reads
  `snakemake.config["existing_capacities"]["grouping_years"]`. That key does not exist in
  `config.default.yaml` (the real key is `grouping_years_power`); verified by dict lookup.
  Any myopic solve with an "m"-suffixed `clusters` wildcard therefore raises KeyError at
  solve time. eur has no equivalent branch. Either a `dead-key`-flavoured registry note or
  an upstream one-word fix.
- `brownfield-and-capacity-vintaging` / registry (pypsa-earth) —
  `existing-baseyear-brownfield` is rated `partial` with the note "heating brownfield call
  is commented out in prepare_sector_network", which understates it substantially. At this
  ref `scripts/add_existing_baseyear.py` defines only `add_build_year_to_new_assets` and
  `add_heating_capacities_installed_before_baseyear`; there is NO
  `add_power_capacities_installed_before_baseyear` and no `add_existing_renewables`
  (eur has both), the heating call is commented out in the script's own `__main__` behind
  "TODO: not implemented in -sec yet", and the rule's declared `powerplants` and busmap
  inputs are never read (`snakemake.input` is touched only for
  `existing_heating_distribution`, `network`, `costs`). Earth's power vintaging happens
  instead in `scripts/add_electricity.py:aggregate_ppl_by_bus_carrier_year` — the registry
  should point the consumer THERE for the power fleet and keep `partial` for the sector
  rule. Two config keys are dead as a result:
  `existing_capacities.default_heating_lifetime` (occurs only inside the commented-out
  block) and `existing_capacities.conventional_carriers` (occurs nowhere outside
  config.default.yaml; eur's identical key is live via
  `scripts/prepare_sector_network.py:conventional_carriers`).
- `brownfield-and-capacity-vintaging` / registry (pypsa-earth) — no `max-growth-limits`
  id, correctly: there is no `limit_max_growth` config key and no `add_max_growth`
  function. Recording it because eur's is `partial` and the reason is upstream, not
  configural — pypsa's `optimization/global_constraints.py:define_growth_limit` returns
  immediately unless `n._multi_invest`, so growth caps are unreachable in ANY model
  without perfect foresight. Worth an `absent` entry so the asymmetry is routable.
- `brownfield-and-capacity-vintaging` / both models — the land/resource decrement is
  gated on foresight (`myopic`/`perfect` in eur, `myopic` only in earth), so an OVERNIGHT
  brownfield run never decrements p_nom_max by existing vintages in either model. Every
  earth-family paper in this corpus is overnight. This is the card's worst silent failure
  and it has no registry surface at all; a referee fixture check on
  `p_nom_max >= p_nom_min` plus a comparison against the undecremented potential is the
  cheapest guard.
- `brownfield-and-capacity-vintaging` / both models — no summary table splits capacity by
  `build_year`, so the retirement schedule and stranded-annuity figures that Victoria 2020
  reports as headline results must be computed outside the workflow. Note for the
  extraction/metrics book: earth is easier here because its cohort naming
  (`<bus> <carrier>-<year>`, from `aggregate_ppl_by_bus_carrier_year`) makes the vintage
  recoverable from the component index, whereas eur's needs `build_year` off the component
  frame.
- `demand-side-flexibility-representation` / registry (pypsa-earth) — `bev-dsm-v2g`'s
  `surface` is WRONG, not merely vague: it reads
  `sector.land_transport.{bev_dsm,v2g,bev_availability,...} (verify exact keys per recipe)`
  but there is no `land_transport` sub-mapping under `sector` in
  `models/pypsa-earth/config.default.yaml`. The keys are FLAT: `sector.bev_dsm`,
  `sector.v2g`, `sector.bev_availability`, `sector.bev_dsm_restriction_{value,time}`,
  `sector.bev_avail_{max,mean}`, `sector.bev_energy`, `sector.bev_charge_efficiency`. A
  bundle written from that surface would set a nested key nothing reads and the run would
  succeed with default flexibility — the exact silent failure the config rule exists to
  prevent. Also note earth's participation key is `bev_availability` where eur's is
  `bev_dsm_availability`, so the two registries' surfaces are not interchangeable.
- `demand-side-flexibility-representation` / registry (pypsa-earth) — three eur ids have no
  earth counterpart at all, and all three are load-bearing for this method:
  `residential-heat-dsm`, `industry-t-endogenous` and `tes-constraints`. Grep confirms
  earth has NO `residential_heat`, no `heat dsm`, no `overheat`/`undercool`, no
  `industry_t` and no `must_run` anywhere in `scripts/`, and no `add_TES_*` function in
  `solve_network.py`. Registry silence reads as "unexamined"; these should be explicit
  `absent` ids, because the asymmetry (eur has three flexibility constructions, earth has
  one) is the payload an interview needs.
- `demand-side-flexibility-representation` / registry (both models) — no id covers
  minimum-part-load as a flexibility surface, although
  `sector.min_part_load_electrolysis` (eur, default 0) is live at
  `scripts/prepare_sector_network.py` and is the ENTIRE lever for the
  flexible-electrolysis variant that four corpus papers use. Earth has only
  `sector.min_part_load_fischer_tropsch` (0.9) and no electrolysis equivalent, so an
  electrolyser there is unconditionally flexible with no way to build the no-DSM
  counterfactual. Both need ids: `working` for eur, `absent`/`partial` for earth. Same
  applies to ramp limits, which no `n.add('Link', ...)` in either model sets for
  electrolysis.
- `demand-side-flexibility-representation` / models[pypsa-earth] — two DEFECTS in
  `scripts/prepare_sector_network.py:add_land_transport` that no registry id records and
  that the card had to assert as `boundary` L2 plus a failing `verifies` check. (1) The
  ` V2G` Link is created with `p_nom=p_nom`, the full charger rating, where eur uses
  `p_nom * options["bev_dsm_availability"]` — so at the shipped `bev_availability: 0.5`
  earth exports at twice the participating fleet's charger power while the Store holds
  only half the fleet's energy. (2) The V2G branch is `if electric_share > 0 and
  options["v2g"]`, a sibling of the `bev_dsm` branch rather than nested inside it as in
  eur, so `v2g: true` with `bev_dsm: false` builds discharge Links from a bus with no
  Store. Neither errors. Both deserve a `broken`/`partial` downgrade of earth's
  `bev-dsm-v2g` from `working`, or at minimum a note.
- `demand-side-flexibility-representation` / models[pypsa-earth] — `sector.bev_charge_rate`
  does NOT exist in earth's `config.default.yaml`, but
  `scripts/prepare_sector_network.py` reads it as `options.get("bev_charge_rate", 0.011)`.
  The per-car charger rating — i.e. the POWER limit on EV flexibility, which this card's
  pitfalls identify as the parameter idealised studies wrongly omit — is therefore not
  configurable in earth. This is the inverse of a dead key: a live consumer with no
  config surface, which no registry status value currently expresses. Worth a
  vocabulary addition (`missing-key`?) or a note on `bev-dsm-v2g`.
- `demand-side-flexibility-representation` / data (pypsa-earth) —
  `data/emobility/Pkw__count` is German car-count data, shipped as one file and consumed
  by `scripts/prepare_transport_data.py` for EVERY country earth can model. The
  plugged-in availability profile that bounds all EV flexibility therefore carries German
  weekly commuting behaviour into any region. `cookbooks/pypsa-earth/data_quality` should
  carry this as an explicit grade-C/D entry against transport flexibility; today it is
  invisible and an agent would report an EV-flexibility number for Nigeria without
  flagging it. Earth also lacks eur's negative-availability warning in the same
  scaling code, so an inconsistent `bev_avail_max`/`bev_avail_mean` pair fails silently.
- `demand-side-flexibility-representation` / `available.verdict` (pypsa-earth) — rated
  `assemble`, but the honest statement is narrower than that word suggests and the schema
  has no value for it: ONE of the eight constructions ships complete, four are absent in
  both code and data, and all of them are gated behind the sector chain so an
  electricity-only earth run has no endogenous demand flexibility at all beyond load
  shedding. `assemble` implies "every surface exists; you wire them", which is true of the
  EV variant and false of the rest. A per-variant verdict (rather than one per model)
  would express this; the boundary ladder carries it instead.
- `demand-side-flexibility-representation` / `verifies` — the two checks that would
  actually catch this method's characteristic failure are cross-run, not per-network:
  "baseline and flexible runs serve identical total service demand" and "the flexible
  run's Store energy series has a DAILY period, not a seasonal one". The first is
  authored `over: ensemble` and needs `referee/check_ensemble.py` (absent) plus a
  convention for which network in the ensemble is the baseline — the current contract
  does not say whether ensembles are ordered or labelled. The second needs a
  spectral/autocorrelation test on `n.stores_t.e`, which is a different shape of check
  from anything the referee contract currently expresses. No fixture contains a Store with
  a time-varying `e_min_pu`, so every check on this card is authored and unexercised.
- `demand-side-flexibility-representation` / variants `spatio-temporal-shifting`,
  `price-elastic-demand` — both rated L5 in both models from the absence of any
  implementation, which is solid. What is NOT grounded is the assembly detail. Riepin
  2024's virtual-link graph, daily usage-conservation constraint and (1 +/- f) band are
  recorded from pass 1's `procedure_notes` by equation NUMBER, not content, so the card
  describes the construction's shape but cannot state the constraint algebra. Same for
  Brown 2025's piecewise-linear log-log form: the parameter triples are recorded but the
  segment-to-generator mapping and the numerical-stabilisation substitution are known only
  as prose. Authoring a real `assembly` for either would need the PDFs, which pass 2
  forbids.
- `extreme-event-and-dunkelflaute-analysis` / `procedure` steps 2-4 (the meteorological
  detector) — pass 1's `procedure_notes` give Mockert's weights (44/50/6%), threshold
  (0.06), window (48 h) and event counts, which is enough to state the algorithm. What is
  NOT grounded is the weather-regime construction itself: "EOF + k-means on z500" is
  recorded only as a phrase in `unmatched_methods`, so the card cannot say how many EOFs
  are retained, whether anomalies are seasonally detrended, or what domain the seven
  North-Atlantic-European regimes are defined over. Writing a real `assembly` for the
  `weather-regime-classification` variant would need the Mockert PDF (and its cited
  regime-definition source), which pass 2 forbids. The variant is therefore rated L3 from
  the DATA gap (no z500 retrieval in either model), which is solid, while its recipe stays
  deliberately thin.
- `extreme-event-and-dunkelflaute-analysis` / `procedure` step 7 (de-overlapping and event
  extension) — recorded from Grochowicz 2023 SI A.3 as "order from shorter/more-expensive
  to longer, then extend while event-average hourly cost does not decrease". The ordering
  is a greedy rule whose tie-breaking and exact objective are not in the slice, so a
  reimplementation cannot be bit-compatible with the published event set. Would need the
  2023 SI.
- `extreme-event-and-dunkelflaute-analysis` / `verifies` — the cross-year stress-test
  postconditions that matter are all `over: ensemble` (ensemble size == designs x stress
  years; identification runs have no shedding generators) and need
  `referee/check_ensemble.py`, which does not exist. The per-run checks are authored
  against attributes that no current fixture exercises: no fixture has a network with
  `p_nom_extendable` already fixed by a prior solve, and none carries load-shedding
  generators, so the two highest-value checks on this card (capacities actually frozen;
  shedding actually present) are unexercised. A fixture pair — one expansion-solved
  network plus its operations-only re-solve — would exercise most of them.
- `extreme-event-and-dunkelflaute-analysis` / REGISTRY CORRECTION, not a gap in this card:
  `safe-reserve-margin` is rated `working` for pypsa-earth and `partial` for pypsa-eur on
  the grounds that eur lacks a shipped `electricity.SAFE_reservemargin` key. At
  8435f4c8 earth does not ship it either — it appears only inside
  `scripts/solve_network.py:add_SAFE_constraints`' docstring, and the constraint function
  reads `config["electricity"]["SAFE_reservemargin"]` unguarded, so a SAFE token in
  `scenario.opts` KeyErrors on the default config. Earth's status should be `partial` to
  match eur. Worth fixing in `cookbooks/pypsa-earth/topics/FUNCTIONALITY.yaml`.
- `operational-dispatch-and-rolling-horizon` / `procedure` step 7 (terminal value for
  stored energy at a window boundary): only ONE paper in the slice supplies a mechanism
  (Brown 2025's constant marginal-storage-value bid = mean of the long-term model's
  storage shadow price), so the step is written from a single source and the card cannot
  say whether state-of-charge-dependent bids or an explicit end-of-window value function
  are used elsewhere in the wider literature. Would need papers outside this corpus
  (the water-value / SDP hydro-scheduling literature) to write it properly.
- `operational-dispatch-and-rolling-horizon` / `variants[market-aligned-multistage-dispatch]`:
  Welfonder 2024 is the only source, and pass 1's notes give the three stages and their
  gate-closure times but not how the stochastic scenario tree is reduced between stages
  or how many draws per stage. The variant is therefore described at the level of its
  information structure only. Would need the PDF's Sec. 2.3-2.4 to write the procedure.
- `operational-dispatch-and-rolling-horizon` / UPSTREAM DEFECTS worth reporting to
  pypsa-eur (verified at 849c8858, all silent failures):
  (1) `scripts/solve_operations_network.py` calls `prepare_network(...)` WITHOUT
  `rolling_horizon=`, so the cyclic-storage teardown that `solve_network.py` performs is
  skipped in the dedicated operations rule — this is exactly the failure Karkossa 2026
  reports (cyclic hydro reservoir constraint per window caused load shedding in Norway).
  (2) The same file does `all_kwargs, _ = collect_kwargs(..., mode="single")`, but
  `mode="single"` returns `(model_kwargs, solve_kwargs)`; `solve_kwargs` is discarded, so
  the non-rolling operations solve runs on pypsa's default `solver_name="highs"` and
  ignores `solving.solver` entirely.
  (3) The string `extra_functionality` does not occur in that file at all, so CO2 caps,
  CCL/BAU/SAFE constraints, operational reserves and `custom_extra_functionality` are all
  dropped from the operations re-solve — even though rule `solve_operations_network`
  declares `custom_extra_functionality` in its `params`.
  Consequence for the card: route A (empty `electricity.extendable_carriers` and solve
  through rule `solve_network`) is recommended over route B until these land upstream.
- `operational-dispatch-and-rolling-horizon` / REGISTRY NOTE, not a gap in this card:
  `cookbooks/pypsa-earth/topics/FUNCTIONALITY.yaml` has no `rolling-horizon-dispatch`
  entry at all, which is correct (earth has no such surface) but means the index shows
  `--` rather than `absent`. Given how load-bearing the eur/earth asymmetry is here, an
  explicit `absent` entry citing the comment-only vestige in
  `scripts/solve_network.py` (`if status != "ok":  # and not rolling_horizon:`) would be
  more useful to an interview than silence. Also: earth's
  `doc/user-guide/rules-reference/solving/index.md` claims a `solve_operations_network`
  rule exists; no such rule exists anywhere in the repo (inherited pypsa-eur docs).

## discounting-and-cost-of-capital

- **`literature[].note` for 26 of 43 papers is thin by necessity, not by omission.**
  40 of 43 papers carry role `routine-use` and their pass-1 `procedure_notes` say only
  "uniform 7%, no country- or technology-specific differentiation". Those notes are
  written as one-line rate records (a table of what the field assumes) rather than as
  method contributions, which is the honest representation. To say more would need the
  papers' cost tables, not their methods sections.
- **`pitfalls` has ZERO `critiques`-role papers to draw on.** Every pitfall on the card
  is derived from the models' code (verified by grep) or from a `canonical-use` paper's
  own methodological statement, not from a paper criticising the method. This is the
  only card in the top ten by prevalence with no critique literature at all. What would
  close it: a paper examining how the uniform-7% convention biases technology choice.
  Schyska 2020 is the closest the corpus has and it is a sensitivity study, not a
  critique — it does not argue the convention is wrong, only that it is consequential.
- **`cost-data-pipeline` has no `pypsa-earth` registry entry**, so the earth section
  cites `discount-rate-dimension` for a capability (cost preparation, currency
  conversion, annuity computation) that plainly exists there — `scripts/process_cost_data.py`
  has `load_costs`, `prepare_costs`, `annuity`, `apply_currency_conversion` and
  `get_yearly_currency_exchange_rate`. An earth `cost-data-pipeline` entry (status
  `working`, surface `costs.{year,technology_data_version,output_currency,
  default_exchange_rate,future_exchange_rate_strategy,custom_future_exchange_rate,
  rooftop_share,fill_values,marginal_cost}`, consumer
  `scripts/process_cost_data.py:load_costs`) would make the eur/earth comparison on this
  card a registry lookup instead of a grep. Earth's currency machinery has no eur
  counterpart and currently appears in no registry at all.
- **`cascading-failure-analysis`: no registry id exists for post-hoc network analysis.**
  The card cites `contingency-scopf` (status `absent` on both models) as its nearest
  registry entry, but that id is about security inside the OPTIMISATION. There is no
  FUNCTIONALITY id for "consumes a solved network and analyses its topology" on either
  model — no cascade, no LODF/BODF screening, no islanding, no lost-load accounting.
  Every other card can point at an id that names its capability even when the status is
  `absent`; this one cannot, so the `absent` verdict rests on the author's greps
  (`cascad`/`LODF`/`BODF`/`branch_outages`/`overload` = zero hits in both repos) rather
  than on a registry lookup. What would close it: a `cascade-failure-simulation` entry
  (status `absent`, surface `—`, note naming pypsa/contingency.py:network_lpf_contingency
  as the library primitive and `line-security-margin` as the only related surface) in
  both registries. Related: a `post-solve-network-analysis` id would also serve
  `extreme-event-and-dunkelflaute-analysis`.
- **`cascading-failure-analysis`: `coupled-infrastructure-cascade` is thin.** The slice's
  evidence for Titz 2026 documents the ELECTRICITY cascade in full procedural detail but
  says nothing about how the coupling to non-electrical infrastructures is actually
  represented — the paper's title and framing assert it, the extracted
  `procedure_notes` cover only DC flows, RoCoF and the N-2 sweep. The variant is
  therefore written as "same engine plus a dependency map you must supply" and rated L3
  on data grounds, which is defensible but is an inference from the framing, not from
  extracted method text. What would close it: the paper's section on the
  infrastructure-dependency model — specifically whether dependent infrastructures are
  modelled as loads on electrical buses or as a separate coupled graph, and where the
  dependency data came from.
- **`cascading-failure-analysis`: `prevalence` counts a paper pass 1 assigned elsewhere.**
  Gazafroudi 2021 (Network Boosters) is counted as the third paper for the
  `corrective-action-cascade` variant; pass 1 routed it entirely to
  `n-1-security-and-contingency` (role `defines`) and it is genuinely a preventive/
  corrective SCOPF, not a cascade simulation. It is counted here because no other corpus
  paper models an action taken between tripping rounds and the variant would otherwise
  have no evidence at all. Pass 1.5 should decide whether cross-slug double-counting of
  this kind is acceptable; if not, drop it to `papers: 2` and delete the variant's
  `papers` list rather than the variant.
- **`endogenous-technology-learning`: `variants[].papers` is empty for
  `multi-technology-spillover`.** No paper in the corpus exercises learning that crosses
  technology boundaries; Zeyen 2023's four technologies each learn from their own
  cumulative capacity only. The variant is kept because it is the standard next
  generalisation and because a user asking for it must be told there is no PyPSA
  precedent — but its `papers` list is legitimately empty and the card says so in `what`.
  To fill it would need a paper outside this corpus (the spillover literature is largely
  IAM-side, e.g. shared power-electronics or stack learning). Pass 1.5 should decide
  whether an evidence-free variant is acceptable or whether it should be demoted to a
  line in `pitfalls`.
- **`endogenous-technology-learning`: only 2 papers, and one of them does not run the
  method inside the optimisation.** Franken 2025 (`extends`) estimates a learning rate
  EX POST from an LP sweep; only Zeyen 2023 (`defines`) puts the curve in the objective.
  Every quantitative parameter on the card (segment count, interpolation points, the four
  learning rates, the temporal delay, the global/local split, the ~21 h / ~30 GB cost,
  the <5% sequential convergence threshold) therefore rests on a SINGLE paper. That is
  recorded rather than padded, but it means the card cannot cross-check any of those
  numbers. Would need a second endogenous-learning PyPSA study in the corpus.
- `stochastic-and-robust-optimisation` / registry (both models) — neither
  `cookbooks/pypsa-eur/topics/FUNCTIONALITY.yaml` nor the pypsa-earth one has ANY id for
  stochastic programming, recourse structure, non-anticipativity, or worst-case/min-max
  objectives. The card had to hang its `functionality` citations on `mga-near-optimal`
  (`absent` in both) as the nearest neighbour, which understates the gap: MGA at least has
  a pypsa primitive, and this has none. Two `absent` ids are missing from both registries:
  one for "scenario-indexed / two-stage stochastic program (recourse + non-anticipativity)"
  and one for "scenario generation and reduction (tree construction)". Recommended note
  for both: "no scenario dimension exists on any optimisation variable; pypsa 0.30.3 has no
  primitive; grep for scenario_tree/non_anticipativ/recourse/stochastic/first_stage returns
  zero across both repos at these refs".
- `stochastic-and-robust-optimisation` / `variants[min-max-robust].papers` — empty. NO
  paper in the 100-PDF corpus runs a min-max / worst-case program on a PyPSA model, so the
  variant is authored from the method literature's standard epigraph construction and from
  what the models lack, not from corpus evidence. It is kept because users ask for
  "robust optimisation" by name and the card must be able to answer honestly. Filling it
  would need corpus papers outside the PyPSA family, which is out of this book's scope.
- `stochastic-and-robust-optimisation` / `prevalence` counts two papers pass 1 assigned
  elsewhere. 2022_Grochowicz (pass 1: `mga-near-optimal-space`) and 2020_Schyska (pass 1:
  `sensitivity-and-uncertainty-sweeps`) are counted here as `extends`, on the grounds that
  their `unmatched_methods` entries (`near-optimal-space intersection and chebyshev-centre
  robust design`, `misallocation-metric`) are genuine robust-design and regret constructs.
  Both remain in their original cards' literature, so this is deliberate cross-slug
  double-counting of the same kind `cascading-failure-analysis` flags. Pass 1.5 should
  rule on it once rather than per card; if disallowed, drop to `papers: 2` and delete the
  `chebyshev-centre-robust-design` variant's `papers` list (not the variant, which the
  model sections' ladders need).

## cost-allocation-and-equity-metrics

- **`literature` is missing three papers the orchestrator expected**, and the hard rule
  (no PDF access in pass 2) means I could not add them. Pass 1 attributed
  `2025_Zeyen_Shifting-burdens-road-transport_ERL.pdf` and
  `2017_Schlachtberger_Benefits-Cooperation-Renewable-Network_Energy.pdf` to OTHER slugs
  only (sensitivity-and-uncertainty-sweeps, foresight-and-planning-horizons,
  discounting-and-cost-of-capital, transmission-expansion-cooptimisation,
  shadow-prices-and-marginal-values, carbon-constraints-and-pricing) with no
  cost-allocation evidence recorded, and `2018_Hofmann_Principal-flow-patterns_EPL.pdf`
  only to spatial-clustering-and-resolution and linearised-optimal-power-flow. Schlachtberger
  2017 is very likely the corpus's original "who gains from cooperation" analysis and
  Zeyen 2025's title is literally about shifting burdens; both are probably `defines`/
  `extends` on this card. What would close it: a pass-1 re-read of those three PDFs
  scoped to cost allocation / burden sharing / benefit-of-cooperation sections. Two of
  the six papers on the card were recovered from `unmatched_methods` instead (Tranberg's
  flow tracing, vanGreevenbroek's self-sufficiency constraint), which suggests pass 1's
  slug matcher under-fires on this method generally — its evidence is usually in a
  results/discussion section rather than a methods section.
- **`pitfalls` has ZERO `critiques`-role papers.** Every pitfall is derived from the
  models' code (grep-verified) or from a paper's own stated caveat. The card's central
  claim — that cost attribution is not unique and different defensible rules disagree —
  is asserted from the existence of four incompatible rules in the corpus rather than
  from a paper that measures the disagreement. What would close it: a paper comparing
  allocation rules on the same network and reporting the spread. The corpus appears not
  to contain one.
- **`household-or-consumer-class-incidence` has an empty `papers` list.** It is a real
  variant (users ask for it; both models cannot do it) but no paper in my slice performs
  it, so it is grounded only in the models' absence of household representation. The
  checker permits this; it is flagged so a later pass does not read the empty list as an
  oversight.
- **Two registry corrections found, not yet applied** (a method card must not edit the
  registry): (1) `cookbooks/pypsa-earth/topics/FUNCTIONALITY.yaml:equity-self-sufficiency`
  notes that EQ's trailing `c` means "carbon-free sources only". The code
  (`scripts/solve_network.py:add_EQ_constraints`) switches the GROUPER from
  `n.generators.bus` to `n.generators.bus.map(n.buses.country)` — `c` means per-country,
  and all carriers count. The note is wrong and should be fixed at source. (2) Neither
  registry records `solving.options.assign_all_duals`, which is absent from
  pypsa-eur's `config/config.default.yaml` AND from `scripts/lib/validation/` yet is read
  live at solve time via `cf_solving.get("assign_all_duals", False)` in
  `scripts/solve_network.py:solve_network` and forwarded to `n.optimize`. This is an
  undocumented, schema-less but LIVE config key — exactly the class of thing
  `referee/check_config.py` is meant to catch, and it will currently fail a valid bundle
  that sets it. It is also load-bearing for this card: without it there is no line/link
  `mu_upper` and therefore no congestion rent for any dual-based allocation rule.
