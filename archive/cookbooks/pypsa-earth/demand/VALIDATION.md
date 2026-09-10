# Demand cookbook — validation

## QA (both model sections, mechanical)

`_qa/check_recipes.py` — **36/36 recipes pass**: 1–2 model sections each
(`pypsa-earth` anchored `8435f4c8`, `pypsa-eur` anchored `3e32e3c6`), provenance
`file:symbol` resolved against the section's OWN repo with symbols grep-verified
verbatim, lever keys resolved as dot-paths in the respective default config,
`demand_dimensions` complete where present, `reference_taxonomy` URLs confined to
that block, no line numbers, no verification fields.

## Runtime validation (pypsa-earth side)

Asserted against the ALREADY-BUILT coarse Mexico networks from the
generation_conversion validation (no new model runs): the sector prenetwork
`results/mexico-sector/prenetworks/elec_s_4_ec_lcopt_Co2L_144h_2030_0.071_AB.nc`
and the solved 10-cluster power network. pypsa-eur sections are grounded by
provenance QA only — running pypsa-eur was out of scope.

Produced by `_qa/assert_demand_loads.py`:

| recipe | check | result | detail |
|---|---|---|---|
| electricity-load | AC electricity loads with hourly profiles | PASS | 10 loads, 168 snapshots |
| residential-space-heating-demand | residential heat loads (rural/urban systems) | PASS |  |
| residential-electricity-demand | electricity residential loads | PASS |  |
| services-electricity-demand | services electricity loads | PASS |  |
| services-heat-demand | services heat loads | PASS |  |
| district-heating-demand-share | urban central heat load (config potential*progress) | PASS |  |
| land-transport-demand | EV + fuel cell + oil land transport loads | PASS |  |
| rail-transport-demand | rail transport loads | PASS |  |
| aviation-demand | kerosene for aviation loads | PASS |  |
| shipping-demand | shipping loads | PASS |  |
| agriculture-energy-demand | agriculture electricity + oil loads | PASS |  |
| steel-demand / chemicals-demand / ... (industry families) | industry electricity + gas/biomass for industry loads | PASS |  |
| chemicals-demand | NH3 (ammonia) demand load | PASS |  |
| industrial-process-emissions | process emissions load | PASS |  |
| industrial-feedstocks-nonenergy | H2 / naphtha-type industry loads (report what exists) | PASS | H2-for-industry=4, naphtha=4 |
| demand-temporal-profiles | EV load profile is time-varying (weekly traffic shape) | PASS |  |
| demand-temporal-profiles | heat load profiles time-varying (degree-days) | PASS |  |
| hydrogen-export-demand | EXPECTED ABSENT in prenetwork (export added by add_export at solve stage) | PASS |  |

18/18 checks pass

## Findings surfaced during extraction (grounded, possibly upstream-relevant)

- **pypsa-earth rail overlap**: non-electric rail is folded into the land-transport
  pool (`prepare_transport_data.py`) AND added as a separate `rail transport oil`
  load (`add_rail_transport`) — both facts grounded; potential double-count,
  recorded without asserting a bug (see `rail-transport-demand.yaml`).
- **pypsa-earth `create_industry_base_totals`**: the drop of the "other" industry
  column is unassigned, so the column persists (see `mining-construction-demand.yaml`).
- **pypsa-earth distribution weights hardcoded**: the 0.6·GDP + 0.4·population
  electricity-load split is not configurable (see `demand-spatial-disaggregation.yaml`).
- **pypsa-earth naphtha**: the ENTIRE industrial oil column becomes a
  `naphtha for industry` load — no energy/feedstock split
  (see `industrial-feedstocks-nonenergy.yaml`).
- **pypsa-eur cooking**: JRC cooking columns are parsed but non-electric cooking
  fuel builds NO network load — dropped from demand entirely
  (see `cooking-energy-demand.yaml`).
- **pypsa-eur vestigial keys**: `sector.electricity_distribution_grid_cost_factor`
  defined but no consumer found at `3e32e3c6`; same for earth's
  `sector.ammonia.co2_t_per_tNH3` (re-confirmed independently by two agents).
- **Hint corrections that made it into recipes** (extraction self-corrected):
  earth industry demand is shaped ONLY by `industry_growth_cagr.csv` (the
  efficiency-gains CSV has no industry columns); earth LV distribution losses are
  a 3 % load deduction, not link efficiency; eur pulp has no black-liquor credit.

## Sources for the FORECAST reference_taxonomy blocks

- https://www.forecast-model.eu/forecast-en/content/methodology.php
- https://www.sciencedirect.com/science/article/pii/S2211467X18300890
- https://irees.de/wp-content/uploads/2020/06/1-031-16_Rehfeldt.pdf
- https://github.com/fraunhofer-isi/forecast-sites
