# FUNCTIONALITY registry index (GENERATED — do not edit)

One line per capability id in each model's `cookbooks/<model>/topics/FUNCTIONALITY.yaml`.
Method cards CITE these ids in `models[].functionality[].id` and `assembly[].uses`.
This index exists so a card author does not load 1200 lines of registry: find your
5-8 ids here, then grep the full file for their `surface:` and `consumer:` lines.

119 distinct ids across both registries (pypsa-eur has 105, pypsa-earth 68).
`--` means the id is ABSENT FROM THAT REGISTRY, which is different from
`absent` (present in the registry, verdict: the model does not have it).

| id | eur | earth | title |
|---|---|---|---|
| `administrative-clustering` | working | -- | Administrative (NUTS/bidding-zone) clustering |
| `ammonia-value-chain` | working | working | Ammonia production/consumption chain |
| `ates-potentials` | dead-key | -- | Aquifer thermal energy storage (ATES) |
| `augmented-line-connection` | -- | partial | Connectivity augmentation (k-edge candidate lines) |
| `autarky` | partial | working | Autarky enforcement |
| `base-network-source` | working | -- | Base grid topology source choice |
| `battery-charger-ratio` | partial | -- | Battery charger/discharger sizing coupling |
| `bau-minimum-capacities` | partial | working | System-wide minimum carrier capacities (BAU) |
| `bev-dsm-v2g` | working | working | EV battery demand-shifting and V2G |
| `bidding-zone-shapes` | working | -- | Bidding-zone shape construction |
| `building-retrofit-endogenous` | partial | -- | Endogenous building retrofitting |
| `carbon-intensity-metrics` | partial | partial | Grid carbon intensity (gCO2/kWh) reporting |
| `carrier-attribute-scaling` | working | working | Per-carrier cost/potential scaling (adjustments) |
| `cf-config-injection` | working | -- | Arbitrary config override from wildcard (CF+) |
| `chp-operation-constraints` | dead-key | dead-key | CHP back-pressure / iso-fuel operating envelope |
| `co2-atmosphere-constraint` | working | -- | Non-cyclic co2 atmosphere store constraint |
| `co2-budget-pathway` | working | -- | Carbon budget pathway (co2_budget / cb token) |
| `co2-cap` | working | working | CO2 emission cap, electricity chain (Co2L) |
| `co2-network-sequestration` | working | working | CO2 transport, spatial sequestration & DAC |
| `co2-sequestration-limit` | working | -- | CO2 sequestration budget |
| `config-schema-validation` | working | -- | Config schema validation (pydantic) |
| `contingency-scopf` | absent | absent | True N-1 contingency / security-constrained OPF |
| `copperplate-regions` | working | -- | Copperplating selected regions |
| `cost-data-pipeline` | working | -- | Cost preparation & custom cost overrides |
| `country-carrier-capacity-limits` | working | working | Per-country per-carrier capacity min/max (CCL) |
| `curtailment-mode` | working | -- | Explicit curtailment accounting mode |
| `custom-busmap` | working | working | User-defined zonal map / bus shapes |
| `custom-constraint-hook` | working | working | Custom extra_functionality hook at solve time |
| `custom-data-overrides` | -- | working | Custom user-data override channels |
| `data-retrieval-bundles` | -- | working | Automated open-data retrieval (databundles, OSM, cutouts) |
| `data-retrieval-versioning` | working | -- | Automated versioned data retrieval |
| `demand-elasticity` | absent | absent | Price-elastic / tariff-responsive demand |
| `discount-rate-dimension` | partial | partial | Discount rate as a scenario dimension |
| `distribution-grid-cost-factor` | dead-key | -- | Distribution grid cost factor knob |
| `distribution-grid-lv` | working | partial | Stylized distribution grid (LV bus per node) |
| `distribution-power-flow` | absent | absent | Distribution power flow / hosting-capacity analysis |
| `district-heating-suite` | working | -- | District heating machinery (areas, temperatures, PTES/ATES) |
| `dynamic-emission-pricing` | working | -- | Time-varying CO2 price from ETS spot data (Ept) |
| `dynamic-line-rating` | partial | -- | Dynamic line rating from weather |
| `emission-pricing` | working | working | Static CO2 price (Ep) |
| `end-use-fuel-share-switches` | -- | working | Exogenous end-use fuel/electrification share switches |
| `enhanced-geothermal` | dead-key | -- | Enhanced geothermal systems (EGS) |
| `equity-self-sufficiency` | partial | working | National/nodal self-sufficiency share (EQ) |
| `existing-baseyear-brownfield` | working | partial | Existing capacities in the base year |
| `exogenous-transport-shares` | working | -- | Exogenous land-transport fuel share pathways |
| `financial-viability-actors` | -- | absent | Actor-level finance (utility viability, tariffs, WACC by actor) |
| `fleet-retirement-filter` | working | working | Fleet retirement / commissioning windows |
| `focus-weights` | working | -- | Per-country cluster budget (focus_weights) |
| `fuel-import-supply` | -- | absent | Explicit fuel/energy import supply routes |
| `gadm-admin-clustering` | -- | working | Administrative (GADM) zoning |
| `gas-network-links` | working | dead-key | Methane transmission network with real pipelines |
| `gas-usage-limit` | working | working | Gas consumption budget (CH4L) |
| `geospatial-access-electrification` | absent | absent | Per-settlement electrification (grid vs mini-grid vs SHS) |
| `global-summary` | working | -- | Cross-scenario collected summaries & cumulative costs |
| `green-energy-imports` | working | -- | Green fuel/energy import supply routes |
| `h2-color-accounting` | -- | working | Hydrogen color shares (green/pink/grey) |
| `h2-export-chain` | absent | working | Hydrogen/fuel export demand chain |
| `h2-network-retrofit` | working | -- | H2 pipeline network & gas-pipe retrofitting |
| `h2-pipeline-routing` | -- | working | H2 network buildout / gas-pipeline repurposing |
| `heat-systems-param` | dead-key | -- | sector.heat_systems parameter |
| `hvdc-as-lines` | -- | working | HVDC representation choice |
| `hydro-inflow-normalization` | working | working | Hydro inflow calibration to reported statistics |
| `import-limit-constraint` | working | -- | Green import volume limit |
| `industry-t-endogenous` | working | -- | Endogenous industrial process-heat technology choice |
| `inertia-stability` | absent | absent | System inertia / dynamic stability |
| `interconnection-queues` | absent | absent | Generator interconnection queue / project pipeline modelling |
| `iterative-impedance-expansion` | working | working | Iterative transmission expansion (impedance update) |
| `land-use-constraint` | working | -- | Land-use constraints across horizons |
| `line-security-margin` | working | working | Static N-1 proxy margin on lines |
| `linearized-unit-commitment` | partial | -- | (Linearized) unit commitment & ramping |
| `load-shedding-voll` | working | working | Load shedding at value of lost load |
| `load-sinks` | working | -- | Load sinks (surplus absorption slack) |
| `lossy-bidirectional-links` | working | -- | Lossy bidirectional transmission links |
| `market-design-mechanisms` | absent | absent | Explicit market mechanisms (capacity markets, bidding, ancillary products) |
| `max-growth-limits` | partial | -- | Technology deployment growth limits |
| `methanol-suite` | working | -- | Methanol economy suite |
| `mga-near-optimal` | absent | absent | Modelling-to-generate-alternatives / near-optimal spaces |
| `monte-carlo-sampling` | absent | partial | Monte-Carlo uncertainty fan-out |
| `multi-weather-year` | partial | absent | Multi-year weather in ONE optimization |
| `myopic-foresight` | working | partial | Myopic multi-horizon investment pathway |
| `network-plots` | -- | working | Network & summary plotting |
| `network-simplification` | working | -- | Network simplification to 380 kV |
| `nodal-marginal-prices` | working | working | Nodal shadow prices (LMPs) from duals |
| `numeric-stability-options` | working | working | Numerical hygiene (noisy costs, clipping, seeds) |
| `operational-reserves` | working | working | Operational reserve requirement (GenX-style) |
| `operations-only-solve` | working | absent | Dispatch-only run with fixed capacities |
| `overnight-foresight` | working | -- | Overnight (greenfield) capacity expansion |
| `perfect-foresight` | working | -- | Perfect foresight (multi-investment-period) pathway |
| `pipe-retrofit-constraint` | working | -- | Gas-pipeline to H2 retrofit capacity coupling |
| `plotting-suite` | working | -- | Maps & summary plotting (static + interactive) |
| `post-discretization` | partial | -- | Post-discretization of line/link expansion |
| `probabilistic-adequacy` | absent | absent | Probabilistic resource adequacy (LOLE/EUE, outage draws) |
| `remote-solving-oetc` | partial | -- | Remote cloud solving (OETC) |
| `renewable-potentials-land-eligibility` | working | working | Renewable potentials & land-eligibility chain |
| `residential-heat-dsm` | working | -- | Residential heating demand-side management |
| `retrofit-gas-boiler-constraint` | working | -- | Gas boiler retrofit-to-resistive constraint (perfect only) |
| `rolling-horizon-dispatch` | working | -- | Rolling-horizon optimization |
| `safe-reserve-margin` | partial | working | Planning reserve margin (SAFE) |
| `scenario-matrix` | working | working | Scenario management & cartesian run matrix |
| `sector-coupled-workflow` | -- | working | Sector-coupled model chain (heat/transport/industry/fuels) |
| `sector-master-switches` | working | -- | Sector on/off master switches |
| `shared-resources-caching` | working | -- | Shared-resources caching across runs |
| `solar-potential-constraint` | working | -- | Shared land budget for solar + solar-hsat |
| `solve-statistics` | -- | working | Run/network statistics |
| `solver-choice` | working | working | Solver selection & tuning profiles |
| `spatial-clustering` | working | working | Spatial resolution (clusters wildcard, kmeans/hac) |
| `sub-hourly-resolution` | absent | absent | Sub-hourly temporal resolution |
| `summary-outputs` | working | working | Per-run summary tables (costs, capacities, prices, metrics) |
| `technology-cost-year` | working | working | Technology cost vintage selection |
| `temporal-resolution-nh` | working | working | Temporal averaging (nH resolution) |
| `tes-constraints` | working | -- | Thermal storage energy-to-power & charger-ratio constraints |
| `time-segmentation-tsam` | working | working | Time-series segmentation (nSEG, TSAM) |
| `transmission-expansion-limits` | working | working | Transmission expansion bounds (volume/cost limit) |
| `transmission-losses` | working | -- | Piecewise-linear transmission losses |
| `transmission-projects` | working | -- | Planned transmission project pipeline (TYNDP/NEP) |
| `unit-commitment` | -- | partial | Unit commitment / start-up, min-load, ramping |
| `weather-year-selection` | working | working | Weather year / snapshot window selection |
| `wildcard-opts-grammar` | working | -- | opts / sector_opts token grammar |
| `workflow-reproducibility` | working | working | Pinned, config-driven, re-runnable workflow with provenance |
