# Demand cookbook — index

One recipe per demand kind, covering BOTH pypsa-earth (anchor `8435f4c8`,
2026-07-08) and pypsa-eur (anchor `3e32e3c6`, 2026-06-16, repo
`/home/lukas/Desktop/enderpearl/pypsa-eur`), with FORECAST-inspired
`reference_taxonomy` blocks on the industry cross-cutting topics.
Structural extensions vs generation_conversion: `_qa/SCHEMA_NOTES.md`.
*Entry rung* = lowest rung on that model's boundary ladder; `(proxy)` =
cheapest crude approximation of an uncovered kind. Runtime validation
(pypsa-earth side): `VALIDATION.md`.

## Cross-sector machinery

| topic | slug | pypsa-earth | rung | pypsa-eur | rung |
|---|---|---|---|---|---|
| Baseline electricity load | [`electricity-load`](electricity-load.yaml) | covered | L0 | covered | L0 |
| Demand scenarios & growth scaling machinery | [`demand-scenarios-and-growth`](demand-scenarios-and-growth.yaml) | covered | L0 | covered | L0 |
| Spatial disaggregation of demand to nodes | [`demand-spatial-disaggregation`](demand-spatial-disaggregation.yaml) | covered | L0 | covered | L0 |
| Temporal profiles of demand | [`demand-temporal-profiles`](demand-temporal-profiles.yaml) | covered | L0 | covered | L0 |

## Buildings

| topic | slug | pypsa-earth | rung | pypsa-eur | rung |
|---|---|---|---|---|---|
| Residential space heating demand | [`residential-space-heating-demand`](residential-space-heating-demand.yaml) | covered | L0 | covered | L0 |
| Residential water heating demand | [`residential-water-heating-demand`](residential-water-heating-demand.yaml) | covered | L0 | covered | L2 |
| Services / commercial buildings heat demand | [`services-heat-demand`](services-heat-demand.yaml) | covered | L0 | covered | L0 |
| Residential electricity demand (appliances and lighting) | [`residential-electricity-demand`](residential-electricity-demand.yaml) | covered | L1 | covered | L0 |
| Services / commercial electricity demand | [`services-electricity-demand`](services-electricity-demand.yaml) | covered | L2 | covered | L0 |
| Space cooling / air conditioning demand | [`space-cooling-demand`](space-cooling-demand.yaml) | covered | L0 | covered | L0 |
| Cooking energy demand | [`cooking-energy-demand`](cooking-energy-demand.yaml) | covered | L3 | covered | L0 |
| Building heat demand flexibility / DSM | [`building-heat-dsm`](building-heat-dsm.yaml) | covered | L0 | covered | L0 |

## Transport

| topic | slug | pypsa-earth | rung | pypsa-eur | rung |
|---|---|---|---|---|---|
| Land transport demand (road vehicles) | [`land-transport-demand`](land-transport-demand.yaml) | covered | L1 | covered | L0 |
| Rail transport demand | [`rail-transport-demand`](rail-transport-demand.yaml) | covered | L0 | covered | L2 |
| Aviation demand (kerosene for aviation) | [`aviation-demand`](aviation-demand.yaml) | covered | L0 | covered | L0 |
| Shipping demand (maritime navigation fuels) | [`shipping-demand`](shipping-demand.yaml) | covered | L1 | covered | L0 |
| Agricultural machinery demand (tractors, field machinery) | [`agriculture-machinery-demand`](agriculture-machinery-demand.yaml) | covered | L2 | covered | L0 |

## Agriculture

| topic | slug | pypsa-earth | rung | pypsa-eur | rung |
|---|---|---|---|---|---|
| Agriculture energy demand (farming, forestry, fishing) | [`agriculture-energy-demand`](agriculture-energy-demand.yaml) | covered | L0 | covered | L0 |

## Industry — subsector families

| topic | slug | pypsa-earth | rung | pypsa-eur | rung |
|---|---|---|---|---|---|
| Iron & steel industry demand | [`steel-demand`](steel-demand.yaml) | covered | L0 | covered | L0 |
| Chemicals industry demand (basic chemicals, ammonia, HVC, methanol, chlorine, pharma) | [`chemicals-demand`](chemicals-demand.yaml) | covered | L0 | covered | L0 |
| Cement & non-metallic minerals demand (cement, lime, glass, ceramics) | [`cement-minerals-demand`](cement-minerals-demand.yaml) | covered | L0 | covered | L0 |
| Aluminium & non-ferrous metals demand | [`aluminium-nonferrous-demand`](aluminium-nonferrous-demand.yaml) | covered | L0 | covered | L0 |
| Pulp, paper & printing demand | [`pulp-paper-demand`](pulp-paper-demand.yaml) | covered | L0 | covered | L0 |
| Food, beverages & tobacco demand | [`food-beverages-demand`](food-beverages-demand.yaml) | covered | L0 | covered | L0 |
| Light manufacturing demand (machinery, transport equipment, textiles, wood) | [`light-manufacturing-demand`](light-manufacturing-demand.yaml) | covered | L0 | covered | L0 |
| Mining, quarrying & construction demand | [`mining-construction-demand`](mining-construction-demand.yaml) | covered | L0 | covered | L0 |

## Industry — cross-cutting (FORECAST-inspired)

| topic | slug | pypsa-earth | rung | pypsa-eur | rung |
|---|---|---|---|---|---|
| Industrial process heat by temperature band | [`industrial-process-heat-temperature-bands`](industrial-process-heat-temperature-bands.yaml) | covered | L0 | covered | L0 |
| Industrial process cooling and refrigeration | [`industrial-process-cooling`](industrial-process-cooling.yaml) | not covered | L3 (proxy) | not covered | L2 (proxy) |
| Industrial cross-cutting electricity (motors, compressed air, lighting) | [`industrial-crosscutting-electricity`](industrial-crosscutting-electricity.yaml) | not covered | L3 (proxy) | not covered | L2 (proxy) |
| Industrial feedstocks and non-energy demand (naphtha/HVC, ammonia) | [`industrial-feedstocks-nonenergy`](industrial-feedstocks-nonenergy.yaml) | covered | L0 | covered | L0 |
| Industrial process emissions | [`industrial-process-emissions`](industrial-process-emissions.yaml) | covered | L0 | covered | L0 |
| Industrial material production drivers (tonnes, routes, recycling) | [`industrial-material-production-drivers`](industrial-material-production-drivers.yaml) | covered | L2 | covered | L1 |
| Industrial efficiency measures, technology diffusion and stock turnover | [`industrial-efficiency-diffusion`](industrial-efficiency-diffusion.yaml) | not covered | L2 (proxy) | not covered | L1 (proxy) |

## Other demands

| topic | slug | pypsa-earth | rung | pypsa-eur | rung |
|---|---|---|---|---|---|
| District heating share of heat demand (demand-side allocation) | [`district-heating-demand-share`](district-heating-demand-share.yaml) | covered | L0 | covered | L0 |
| Hydrogen export demand | [`hydrogen-export-demand`](hydrogen-export-demand.yaml) | covered | L0 | covered | L0 |
| Electricity distribution losses as demand | [`electricity-distribution-losses`](electricity-distribution-losses.yaml) | covered | L0 | covered | L0 |
