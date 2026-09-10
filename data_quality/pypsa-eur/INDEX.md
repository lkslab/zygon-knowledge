# Data-quality cookbook — index (generated)

Per-country data-quality scorecards for the **34 countries** in pypsa-eur's default scope (`config/config.default.yaml` `countries:`). Grades: **A** native
country data · **B** global/continental dataset covers it (or not
applicable) · **C** silent DEFAULT/proxy fallback · **D** absent,
feature silently missing. Regenerate:
`pixi run python cookbooks/data_quality/_qa/build_scorecards.py`
(run via the earth repo's pixi env).

## Grade distribution per dataset

| dataset | A | B | C | D |
|---|---|---|---|---|
| jrc-idees | 25 | 0 | 9 | 0 |
| eurostat-balances | 33 | 1 | 0 | 0 |
| swiss-energy-balances | 1 | 33 | 0 | 0 |
| electricity-demand-historic | 34 | 0 | 0 | 0 |
| gb-national-demand | 1 | 33 | 0 | 0 |
| synthetic-demand | 0 | 33 | 1 | 0 |
| powerplantmatching-fleet | 34 | 0 | 0 | 0 |
| osm-grid | 0 | 34 | 0 | 0 |
| tyndp-transmission-projects | 31 | 0 | 0 | 3 |
| scigrid-gas-network | 32 | 0 | 0 | 2 |
| gas-input-locations | 0 | 32 | 0 | 2 |
| enspreso-biomass | 34 | 0 | 0 | 0 |
| hotmaps-industrial-sites | 28 | 0 | 6 | 0 |
| gem-steel-cement-trackers | 0 | 34 | 0 | 0 |
| ammonia-production-usgs | 21 | 0 | 0 | 13 |
| h2-salt-caverns | 16 | 0 | 18 | 0 |
| eia-hydro-annual | 34 | 0 | 0 | 0 |
| hydro-capacities | 30 | 0 | 4 | 0 |
| era5-sarah-cutout | 0 | 34 | 0 | 0 |
| corine-landcover | 0 | 34 | 0 | 0 |
| natura-and-offshore-exclusions | 25 | 0 | 9 | 0 |
| eez | 25 | 9 | 0 | 0 |
| nuts3-population-gdp | 32 | 0 | 2 | 0 |
| worldbank-urban-population | 34 | 0 | 0 | 0 |
| jrc-energy-atlas | 25 | 0 | 9 | 0 |
| district-heating-potentials | 0 | 25 | 9 | 0 |
| retro-building-stock | 25 | 7 | 2 | 0 |
| co2stop-sequestration | 0 | 0 | 34 | 0 |
| transport-data-emobility | 1 | 0 | 33 | 0 |
| unit-commitment-parameters | 0 | 34 | 0 | 0 |
| technology-costs | 0 | 0 | 34 | 0 |
| heat-profile-bdew | 1 | 0 | 33 | 0 |

## Best-covered countries (top 10)

| ISO2 | name | A-grades | D-grades |
|---|---|---|---|
| DE | Germany | 20 A | 0 D |
| BE | Belgium | 18 A | 0 D |
| ES | Spain | 18 A | 0 D |
| FR | France | 18 A | 0 D |
| NL | Netherlands | 18 A | 0 D |
| PL | Poland | 18 A | 0 D |
| RO | Romania | 18 A | 0 D |
| BG | Bulgaria | 17 A | 0 D |
| FI | Finland | 17 A | 0 D |
| GR | Greece | 17 A | 0 D |

## Worst-covered countries (bottom 10)

| ISO2 | name | A-grades | D-grades |
|---|---|---|---|
| GB | United Kingdom | 16 A | 0 D |
| LU | Luxembourg | 15 A | 1 D |
| CH | Switzerland | 13 A | 0 D |
| NO | Norway | 13 A | 1 D |
| RS | Serbia | 11 A | 0 D |
| AL | Albania | 11 A | 1 D |
| BA | Bosnia and Herzegovina | 11 A | 1 D |
| MK | North Macedonia | 9 A | 1 D |
| ME | Montenegro | 9 A | 3 D |
| XK | Kosovo | 6 A | 4 D |

## The silent-fallback (C) datasets to watch

Non-EU27 countries run industry on EU27-average ratios and
residential/services on Eurostat + EU28 splits (no JRC-IDEES); ALL
countries except Germany use the German BASt traffic and BDEW heat
profiles; technology costs are Europe-uniform. These degrade
silently — check a country's scorecard before trusting sector
results. The headline gradient: EU27 core mostly A; CH/NO/GB carry
native substitutes but miss the EU-scoped sources; the Western
Balkans accumulate C/D grades; XK is the worst-covered country in
scope.

Dataset → dependent carrier cards: see `datasets.yaml` (`used_by`).