# Topics cookbook — index

One wiring card per planning/analysis topic (Appendix A of
`energy_topics/energy_modelling_demand_landscape.md`, ranked by urgency).

**`v` is the first thing to read.** A `2` card has been migrated: it links
executable method specs (`methods:`, `*` = not yet verified on this model)
and is usable to scope a study. A `1` card still wires to the capability
registry (`FUNCTIONALITY.yaml`) and **cannot scope a study** — the topic is
real, the wiring for it is not written yet. Say so and stop.

Coverage: **ready** = the standard pypsa-earth workflow answers it;
**partial** = a meaningful slice works with config effort;
**GAP** = core machinery missing (the card says what to build).

| # | topic | v | coverage | recipes | methods | missing functionality |
|---|---|---|---|---|---|---|
| 1 | [Transmission expansion planning](v1/transmission-expansion-planning.yaml) | 1 | ready | 5 | — | `contingency-scopf`, `mga-near-optimal` |
| 2 | [Grid interconnection queues](v1/grid-interconnection-queues.yaml) | 1 | GAP | 4 | — | `interconnection-queues`, `contingency-scopf` |
| 3 | [Data-center load growth](v1/data-center-load-growth.yaml) | 1 | partial | 8 | — | `demand-elasticity` |
| 4 | [Capacity expansion](capacity-expansion.yaml) | 2 | ready | 9 | `existing-fleet`, `pathway-myopic`, `pathway-perfect` | — |
| 5 | [Resource adequacy](v1/resource-adequacy.yaml) | 1 | partial | 7 | — | `probabilistic-adequacy`, `multi-weather-year` |
| 6 | [System flexibility need](v1/system-flexibility-need.yaml) | 1 | partial | 9 | — | `demand-elasticity`, `market-design-mechanisms` |
| 7 | [Cross-border interconnection](v1/cross-border-interconnection.yaml) | 1 | ready | 6 | — | — |
| 8 | [Renewable integration](v1/renewable-integration.yaml) | 1 | ready | 8 | — | `multi-weather-year`, `inertia-stability` |
| 9 | [Net-zero pathways](v1/net-zero-pathways.yaml) | 1 | partial | 8 | — | `mga-near-optimal` |
| 10 | [Battery storage sizing](v1/battery-storage-sizing.yaml) | 1 | ready | 8 | — | `market-design-mechanisms`, `operations-only-solve` |
| 11 | [Long-duration storage (LDES)](v1/long-duration-storage-ldes.yaml) | 1 | ready | 8 | — | `multi-weather-year` |
| 12 | [Curtailment minimization](v1/curtailment-minimization.yaml) | 1 | ready | 7 | — | — |
| 13 | [Demand response](v1/demand-response.yaml) | 1 | partial | 9 | — | `demand-elasticity`, `market-design-mechanisms` |
| 14 | [Dunkelflaute / low-VRE risk](v1/dunkelflaute-low-vre-risk.yaml) | 1 | partial | 6 | — | `multi-weather-year`, `probabilistic-adequacy` |
| 15 | [Locational electricity markets](locational-electricity-markets.yaml) | 2 | partial | 4 | `investment-geography`, `flow-based-market-coupling`, `redispatch`, `pathway-myopic` | — |
| 16 | [Grid congestion / redispatch](v1/grid-congestion-redispatch.yaml) | 1 | partial | 6 | — | `contingency-scopf`, `operations-only-solve` |
| 17 | [Capacity market design](v1/capacity-market-design.yaml) | 1 | GAP | 5 | — | `market-design-mechanisms`, `probabilistic-adequacy` |
| 18 | [Sector coupling](v1/sector-coupling.yaml) | 1 | ready | 12 | — | — |
| 19 | [Distribution hosting capacity](v1/distribution-hosting-capacity.yaml) | 1 | GAP | 7 | — | `distribution-power-flow` |
| 20 | [Smart EV charging](v1/smart-ev-charging.yaml) | 1 | partial | 5 | — | `distribution-power-flow`, `demand-elasticity` |
| 21 | [Coal early retirement](v1/coal-early-retirement.yaml) | 1 | ready | 6 | — | `financial-viability-actors` |
| 22 | [Universal electricity access](v1/universal-electricity-access.yaml) | 1 | GAP | 8 | — | `geospatial-access-electrification`, `distribution-power-flow` |
| 23 | [Geospatial electrification (mini-grid vs grid)](v1/geospatial-electrification-mini-grid-vs-grid.yaml) | 1 | GAP | 6 | — | `geospatial-access-electrification`, `distribution-power-flow` |
| 24 | [Green hydrogen siting](v1/green-hydrogen-siting.yaml) | 1 | ready | 8 | — | — |
| 25 | [Multi-year weather variability](v1/multi-year-weather-variability.yaml) | 1 | partial | 6 | — | `multi-weather-year`, `probabilistic-adequacy` |
| 26 | [Peak demand forecasting](v1/peak-demand-forecasting.yaml) | 1 | partial | 7 | — | `demand-elasticity` |
| 27 | [Firm low-carbon capacity](v1/firm-low-carbon-capacity.yaml) | 1 | ready | 8 | — | `probabilistic-adequacy` |
| 28 | [Solar-to-evening-peak shift](v1/solar-to-evening-peak-shift.yaml) | 1 | ready | 7 | — | — |
| 29 | [Vehicle-to-grid (V2G)](v1/vehicle-to-grid-v2g.yaml) | 1 | ready | 6 | — | `distribution-power-flow` |
| 30 | [Heat pump grid impact](v1/heat-pump-grid-impact.yaml) | 1 | ready | 8 | — | `distribution-power-flow` |
| 31 | [Balancing-market valuation](v1/balancing-market-valuation.yaml) | 1 | GAP | 6 | — | `market-design-mechanisms` |
| 32 | [Ancillary services co-optimization](v1/ancillary-services-co-optimization.yaml) | 1 | GAP | 7 | — | `market-design-mechanisms`, `inertia-stability`, `contingency-scopf` |
| 33 | [Industrial cluster decarbonization](v1/industrial-cluster-decarbonization.yaml) | 1 | partial | 11 | — | — |
| 34 | [Electrolyser grid flexibility](v1/electrolyser-grid-flexibility.yaml) | 1 | ready | 7 | — | `market-design-mechanisms` |
| 35 | [Minimum operational demand](v1/minimum-operational-demand.yaml) | 1 | GAP | 8 | — | `inertia-stability`, `demand-elasticity` |
| 36 | [Rooftop solar saturation](v1/rooftop-solar-saturation.yaml) | 1 | partial | 8 | — | `distribution-power-flow`, `demand-elasticity` |
| 37 | [Electricity-for-industrialization](v1/electricity-for-industrialization.yaml) | 1 | ready | 10 | — | — |
| 38 | [Climate-finance eligibility (gCO2/kWh)](v1/climate-finance-eligibility-gco2-kwh.yaml) | 1 | partial | 8 | — | — |
| 39 | [DISCOM / utility financial viability](v1/discom-utility-financial-viability.yaml) | 1 | GAP | 7 | — | `financial-viability-actors`, `demand-elasticity` |
| 40 | [Seasonal storage gap](v1/seasonal-storage-gap.yaml) | 1 | ready | 9 | — | `multi-weather-year` |
| 41 | [Green ammonia exports](v1/green-ammonia-exports.yaml) | 1 | partial | 6 | — | — |
| 42 | [E-methanol / shipping fuel](v1/e-methanol-shipping-fuel.yaml) | 1 | GAP | 5 | — | — |
| 43 | [Steel decarbonization (H2-DRI)](v1/steel-decarbonization-h2-dri.yaml) | 1 | partial | 8 | — | — |
| 44 | [Cement decarbonization](v1/cement-decarbonization.yaml) | 1 | partial | 6 | — | — |
| 45 | [High-temperature industrial heat](v1/high-temperature-industrial-heat.yaml) | 1 | partial | 6 | — | — |
| 46 | [District heating optimization](v1/district-heating-optimization.yaml) | 1 | partial | 8 | — | `chp-operation-constraints` |
| 47 | [Thermal storage](v1/thermal-storage.yaml) | 1 | ready | 7 | — | — |
| 48 | [Building retrofit pathways](v1/building-retrofit-pathways.yaml) | 1 | partial | 6 | — | — |
| 49 | [Cooling / AC peak demand](v1/cooling-ac-peak-demand.yaml) | 1 | GAP | 5 | — | `demand-elasticity` |
| 50 | [Hydropower drought risk](v1/hydropower-drought-risk.yaml) | 1 | partial | 5 | — | `multi-weather-year` |
| 51 | [Ultra-high-voltage transmission](v1/ultra-high-voltage-transmission.yaml) | 1 | ready | 5 | — | — |
| 52 | [Renewable energy zones](v1/renewable-energy-zones.yaml) | 1 | partial | 7 | — | — |
| 53 | [Offshore wind integration](v1/offshore-wind-integration.yaml) | 1 | ready | 6 | — | — |
| 54 | [Power market reform / spot markets](v1/power-market-reform-spot-markets.yaml) | 1 | GAP | 5 | — | `market-design-mechanisms`, `demand-elasticity` |
| 55 | [Nuclear / SMR role](v1/nuclear-smr-role.yaml) | 1 | ready | 4 | — | — |
| 56 | [CCS / CCU deployment](v1/ccs-ccu-deployment.yaml) | 1 | partial | 7 | — | — |
| 57 | [E-kerosene / aviation fuel](v1/e-kerosene-aviation-fuel.yaml) | 1 | ready | 5 | — | — |
| 58 | [Blue hydrogen economics](v1/blue-hydrogen-economics.yaml) | 1 | ready | 5 | — | — |
| 59 | [Hydrogen network buildout](v1/hydrogen-network-buildout.yaml) | 1 | ready | 7 | — | `gas-network-links` |
| 60 | [Energy-desalination nexus](v1/energy-desalination-nexus.yaml) | 1 | GAP | 5 | — | `demand-elasticity` |
| 61 | [Aggregator / VPP dispatch](v1/aggregator-vpp-dispatch.yaml) | 1 | GAP | 7 | — | `market-design-mechanisms`, `financial-viability-actors`, `demand-elasticity` |
| 62 | [Load-shifting (industrial)](v1/load-shifting-industrial.yaml) | 1 | GAP | 8 | — | `demand-elasticity`, `market-design-mechanisms` |
| 63 | [Asset cost-benefit](asset-cost-benefit.yaml) | 2 | ready | 7 | `existing-fleet`, `single-asset-cba`, `multi-scenario`, `pathway-myopic`, `pathway-perfect` | — |
| 64 | [Extreme-weather resilience](v1/extreme-weather-resilience.yaml) | 1 | partial | 7 | — | `multi-weather-year`, `probabilistic-adequacy` |
| 65 | [Security of supply / imports](v1/security-of-supply-imports.yaml) | 1 | partial | 6 | — | `gas-network-links` |
| 66 | [Biomass / bioenergy allocation](v1/biomass-bioenergy-allocation.yaml) | 1 | ready | 8 | — | — |
| 67 | [Marginal abatement cost curves](v1/marginal-abatement-cost-curves.yaml) | 1 | partial | 6 | — | — |
| 68 | [Stranded-asset risk](v1/stranded-asset-risk.yaml) | 1 | partial | 6 | — | `financial-viability-actors` |
| 69 | [Storage revenue stacking](v1/storage-revenue-stacking.yaml) | 1 | partial | 6 | — | `market-design-mechanisms` |
| 70 | [Fleet EV charging siting](v1/fleet-ev-charging-siting.yaml) | 1 | GAP | 7 | — | `distribution-power-flow` |
| 71 | [Regional power pool modelling](v1/regional-power-pool-modelling.yaml) | 1 | ready | 6 | — | — |
| 72 | [Grid-forming inverters](v1/grid-forming-inverters.yaml) | 1 | GAP | 5 | — | `inertia-stability` |
| 73 | [System inertia / stability](v1/system-inertia-stability.yaml) | 1 | GAP | 6 | — | `inertia-stability`, `contingency-scopf` |
| 74 | [Distributed energy resources (DER)](v1/distributed-energy-resources-der.yaml) | 1 | partial | 8 | — | `distribution-power-flow`, `demand-elasticity`, `geospatial-access-electrification` |
| 75 | [Prosumer / behind-the-meter](v1/prosumer-behind-the-meter.yaml) | 1 | partial | 6 | — | `demand-elasticity`, `financial-viability-actors` |
| 76 | [Time-of-use tariff design](v1/time-of-use-tariff-design.yaml) | 1 | GAP | 6 | — | `demand-elasticity`, `market-design-mechanisms`, `financial-viability-actors` |
| 77 | [Green-H2 export cost benchmarking](v1/green-h2-export-cost-benchmarking.yaml) | 1 | ready | 6 | — | — |
| 78 | [Direct electrification vs H2](v1/direct-electrification-vs-h2.yaml) | 1 | ready | 9 | — | — |
| 79 | [Refinery / chemicals feedstock](v1/refinery-chemicals-feedstock.yaml) | 1 | partial | 6 | — | — |
| 80 | [Waste heat recovery](v1/waste-heat-recovery.yaml) | 1 | GAP | 7 | — | `chp-operation-constraints` |
| 81 | [Demand electrification pathways](v1/demand-electrification-pathways.yaml) | 1 | partial | 9 | — | `demand-elasticity` |
| 82 | [JETP transition financing](v1/jetp-transition-financing.yaml) | 1 | partial | 6 | — | `financial-viability-actors` |
| 83 | [Carbon pricing sensitivity](v1/carbon-pricing-sensitivity.yaml) | 1 | ready | 4 | — | — |
| 84 | [Uncertainty / near-optimal spaces (MGA)](v1/uncertainty-near-optimal-mga.yaml) | 1 | GAP | 0 | — | `mga-near-optimal`, `multi-weather-year` |
| 85 | [Robust decision-making](v1/robust-decision-making.yaml) | 1 | partial | 1 | — | `mga-near-optimal`, `multi-weather-year` |
| 86 | [Open input-data assembly](v1/open-input-data-assembly.yaml) | 1 | ready | 2 | — | — |
| 87 | [Model reproducibility](v1/model-reproducibility.yaml) | 1 | ready | 0 | — | — |
| 88 | [Solver speed / scalability](v1/solver-speed-scalability.yaml) | 1 | ready | 0 | — | `operations-only-solve` |
| 89 | [High-resolution spatial modelling](v1/high-resolution-spatial-modelling.yaml) | 1 | ready | 5 | — | `distribution-power-flow` |
| 90 | [Multi-sector model coupling](v1/multi-sector-model-coupling.yaml) | 1 | partial | 6 | — | `gas-network-links` |
| 91 | [AI-assisted scenario generation](v1/ai-assisted-scenario-generation.yaml) | 1 | GAP | 0 | — | — |
| 92 | [Non-expert model usability](v1/non-expert-model-usability.yaml) | 1 | GAP | 0 | — | — |
| 93 | [Energy affordability / equity](v1/energy-affordability-equity.yaml) | 1 | GAP | 6 | — | `demand-elasticity`, `financial-viability-actors` |
| 94 | [Just transition impacts](v1/just-transition-impacts.yaml) | 1 | GAP | 3 | — | `financial-viability-actors` |
| 95 | [Critical-minerals supply chains](v1/critical-minerals-supply-chains.yaml) | 1 | GAP | 3 | — | — |
| 96 | [Water-energy-land nexus](v1/water-energy-land-nexus.yaml) | 1 | partial | 7 | — | `multi-weather-year` |
| 97 | [Methane / gas phase-down](v1/methane-gas-phase-down.yaml) | 1 | partial | 5 | — | `gas-network-links` |
| 98 | [Synthetic natural gas (e-SNG)](v1/synthetic-natural-gas-e-sng.yaml) | 1 | ready | 5 | — | `gas-network-links` |
| 99 | [Geothermal / niche baseload](v1/geothermal-niche-baseload.yaml) | 1 | partial | 2 | — | — |
| 100 | [Tidal / wave (emerging)](v1/tidal-wave-emerging.yaml) | 1 | GAP | 1 | — | — |
| 101 | [Marginal price prediction](marginal-price-prediction.yaml) | 2 | partial | 8 | `price-formation`, `existing-fleet`, `multi-scenario`, `pathway-myopic`, `flow-based-market-coupling` | — |

**Coverage: 35 ready · 39 partial · 27 gap** (of 101). **Migrated: 4 v2 / 97 v1.**
