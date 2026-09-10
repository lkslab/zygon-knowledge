# Data-quality cookbook — index (generated)

Per-country data-quality scorecards for **160 countries**
(all of `world_iso` excluding Europe — Europe is covered by a different
PyPSA model). Grades: **A** native country data · **B** global dataset
covers it · **C** silent DEFAULT/proxy fallback · **D** absent, feature
silently missing. Regenerate: `pixi run python
cookbooks/data_quality/_qa/build_scorecards.py`.

Build-derived grid evidence available for **104** countries
(from 11 built runs);
fleet evidence for **99**.

## Grade distribution per dataset

| dataset | A | B | C | D |
|---|---|---|---|---|
| demand-growth-cagr | 3 | 0 | 157 | 0 |
| demand-efficiency-cagr | 3 | 0 | 157 | 0 |
| industry-growth-cagr | 3 | 0 | 157 | 0 |
| fuel-shares | 3 | 0 | 157 | 0 |
| district-heating-share | 2 | 0 | 158 | 0 |
| salt-cavern-potentials | 5 | 0 | 0 | 155 |
| al-production | 27 | 0 | 0 | 133 |
| unsd-energy-balances | 0 | 158 | 0 | 2 |
| electricity-demand-forecast | 0 | 160 | 0 | 0 |
| gadm-boundaries | 105 | 55 | 0 | 0 |
| osm-grid | 91 | 69 | 0 | 0 |
| worldpop-population | 105 | 55 | 0 | 0 |
| gdp-raster | 0 | 160 | 0 | 0 |
| era5-cutout | 160 | 0 | 0 | 0 |
| powerplant-fleet | 99 | 61 | 0 | 0 |
| hydro-capacities | 49 | 0 | 111 | 0 |
| eia-hydro-generation | 158 | 0 | 0 | 2 |
| industrial-plant-database | 121 | 0 | 0 | 39 |
| ammonia-plants | 1 | 0 | 0 | 159 |
| german-traffic-proxy | 0 | 0 | 160 | 0 |
| bdew-heat-proxy | 0 | 0 | 160 | 0 |
| global-gis-layers | 0 | 160 | 0 | 0 |

## Best-covered countries (top 10)

| ISO2 | name | A-grades | D-grades |
|---|---|---|---|
| MA | morocco | 14 A | 2 D |
| TN | tunisia | 14 A | 2 D |
| US | united-states-of-america | 9 A | 1 D |
| BJ | benin | 9 A | 2 D |
| CM | cameroon | 9 A | 2 D |
| DZ | algeria | 9 A | 2 D |
| EG | egypt | 9 A | 2 D |
| GH | ghana | 9 A | 2 D |
| MZ | mozambique | 9 A | 2 D |
| NG | nigeria | 9 A | 2 D |

## Worst-covered countries (bottom 10)

| ISO2 | name | A-grades | D-grades |
|---|---|---|---|
| GD | grenada | 2 A | 4 D |
| GL | greenland | 2 A | 4 D |
| GY | guyana | 2 A | 4 D |
| KN | saint-kitts-and-nevis | 2 A | 4 D |
| LC | saint-lucia | 2 A | 4 D |
| MH | marshall-islands | 4 A | 5 D |
| MV | maldives | 2 A | 4 D |
| PW | palau | 4 A | 5 D |
| TL | timor-leste | 2 A | 4 D |
| VC | saint-vincent-and-the-grenadines | 2 A | 4 D |

## The silent-fallback (C) datasets to watch

Countries without native rows in the demand CAGR/fuel-share CSVs run on
the DEFAULT row; ALL countries use the German traffic and BDEW heat
profiles. These degrade silently — check a country's scorecard before
trusting sector-demand results.

Dataset → dependent carrier cards: see `datasets.yaml` (`used_by`).