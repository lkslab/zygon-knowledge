# Recipe book — runtime validation (coarse Mexico run)

The recipe book's claims were validated against an actual pypsa-earth run for
**Mexico** at deliberately coarse resolution (RAM-light by request): 4 clusters,
one week of 2013 snapshots, HiGHS solver, temporal aggregation ONLY in the
sector chain (`sopts: 144h`; power `opts` is plain `Co2L` — no second
resampling pass, avoiding the double time-resolution wildcard problem known
from PyPSA-Eur).

- **Commit**: `8435f4c8cc05f30088933b37b7db497ff860dc53` (2026-07-08); run on 2026-07-21
- **Config**: `configs/scenarios/validation.mexico.yaml` (diff on `config.default.yaml`,
  merged via `scripts/build_test_configs.py:create_test_config` into
  `configs/scenarios/.merged/validation.mexico.yaml`)
- **Lever tests baked into the config**: `csp` added to `electricity.renewable_carriers`
  + `extendable_carriers.Generator`; battery as BOTH `StorageUnit` and `Store`;
  `sector.hydrogen.underground_storage: true` with no MX cavern data (fallback test)

## Runs

| run | target | wall time |
|---|---|---|
| power, solved, 4 clusters | `results/mexico-power/networks/elec_s_4_ec_lcopt_Co2L.nc` | ~21 min (incl. MX OSM download + 6 renewable profiles) |
| sector prenetwork, unsolved | `results/mexico-sector/prenetworks/elec_s_4_ec_lcopt_Co2L_144h_2030_0.071_AB.nc` | ~8 min (reuses all power-side resources) |
| power, solved, 10 clusters | `results/mexico-power/networks/elec_s_10_ec_lcopt_Co2L.nc` | ~2 min (profiles cluster-independent, only cluster→solve reruns) |

Invocations (after the merge step):

```bash
pixi run snakemake -j all --resources mem_mb=25000 --rerun-incomplete \
  <target> --configfile configs/scenarios/.merged/validation.mexico.yaml
```

## Findings worth knowing

1. **4-cluster island collapse (why the 10-cluster variant exists).** Mexico's
   OSM base network has **47 AC synchronous islands** (base.nc: 1771 buses /
   2292 lines). `simplify_network` keeps 4 islands (elec_s.nc: 849 buses).
   Clustering to 4 assigns one cluster per island, so ALL lines become
   intra-cluster and the 4-cluster network has **0 AC lines**. Transmission
   claims are therefore checked on the 10-cluster variant (8 extendable lines).
   Same fragmentation phenomenon as observed in the regional blueprint builds.
2. **District heating appears despite an all-zero `district_heating.csv`** —
   the first draft of this validation expected DH absent for MX and was proven
   WRONG by the run: as `recipes/district-heating.yaml` grounds, only the
   `current` column of the CSV is read; DH build-out is driven purely by config
   `sector.district_heating.potential` (0.3) × `progress` (1). The recipe
   corrected the expectation — the intended direction of travel.
3. **Expected regional absences observed** (they demonstrate the recipes'
   `data_dependencies`, not failures): no PHS (no MX pumped hydro in
   powerplantmatching; brownfield-only mechanism), no underground H2 cavern
   store (no MX row in `data/hydrogen_salt_cavern_potentials.csv`; overground
   H2 tank stores appear instead, as the recipe predicts).
4. **No OCGT extendables despite `OCGT` in `extendable_carriers.Generator`** —
   MX has no existing OCGT fleet, and extendable conventionals are only placed
   at buses already hosting that carrier (`attach_conventional_generators`),
   exactly as the supply-firm recipes document.

## Assertion results (recipe → observable component)

Produced by `recipes/_qa/assert_validation_networks.py`; power checks run on the
10-cluster solved network, sector checks on the 4-cluster prenetwork.

| recipe | check | result | detail |
|---|---|---|---|
| utility-scale-solar-pv | solar generators present + extendable | PASS | 10 gens |
| onshore-wind | onwind generators present + extendable | PASS | 10 gens |
| offshore-wind | offwind-ac generators present + extendable | PASS | 9 gens |
| offshore-wind | offwind-dc generators present + extendable | PASS | 9 gens |
| concentrated-solar-power | csp generators (L1 lever renewable_carriers+=csp) | PASS | 10 gens |
| concentrated-solar-power | csp TES stores + power-block links (csp_model advanced) | PASS | stores=10, links=10 |
| conventional-hydropower | hydro StorageUnits with inflow | PASS | 5 units |
| run-of-river-hydro | ror generators | PASS | 7 gens |
| pumped-hydro-storage | EXPECTED ABSENT: PHS (brownfield-only mechanism; no MX PHS in powerplantmatching) | PASS | 0 units — absence validates the recipe's region-dependent fleet data_dependency |
| conventional-nuclear | nuclear fleet from powerplantmatching | PASS | 1 gens |
| geothermal-conventional | geothermal fleet from powerplantmatching | PASS | 2 gens |
| grid-scale-batteries | battery as StorageUnit (extendable_carriers.StorageUnit) | PASS | 10 units |
| grid-scale-batteries | battery as Store + charger/discharger links | PASS | stores=10 |
| electrolysers | H2 store + electrolysis/fuel cell links (power chain attach_stores) | PASS |  |
| hv-transmission-lines | AC lines extendable under lcopt | PASS | 8 lines |
| hv-transmission-lines | solved: objective finite | PASS | objective=2.234e+10 |
| battery-electric-cars | EV loads + BEV charger links + EV battery buses | PASS |  |
| smart-ev-chargers | EV battery Store (bev_dsm) | PASS |  |
| vehicle-to-grid | V2G links | PASS |  |
| hydrogen-fuel-cell-trucks | land transport fuel cell loads (aggregate H2 road share) | PASS |  |
| rail-electrification | rail transport electricity + oil loads | PASS |  |
| air-source-heat-pumps | air heat pump links | PASS |  |
| ground-source-heat-pumps | ground heat pump links (rural systems) | PASS |  |
| electric-resistance-heating | resistive heater links | PASS |  |
| solar-thermal | solar thermal generators on heat buses | PASS |  |
| thermal-storage | water tank stores + charger/discharger | PASS |  |
| electrolysers | H2 Electrolysis links (production_technologies) | PASS |  |
| blue-hydrogen | SMR + SMR CC links | PASS |  |
| hydrogen-pipelines | H2 pipeline links | PASS |  |
| e-diesel-fischer-tropsch | Fischer-Tropsch links (feed shared oil bus) | PASS |  |
| e-sng | Sabatier / helmeth methanation links | PASS |  |
| green-ammonia | Haber-Bosch links + NH3 buses + ammonia store | PASS |  |
| industrial-ccs | industry CC capture links (gas/biomass for industry CC) | PASS |  |
| electric-arc-furnace | industry electricity loads (aggregate demand-side) | PASS |  |
| biogas-anaerobic-digestion | biogas to gas upgrading link | PASS |  |
| biomass-bioenergy | solid biomass buses/stores | PASS |  |
| beccs | biomass CHP (CC variant = BECCS evidence) | PASS |  |
| direct-air-capture | DAC links into co2 stored | PASS |  |
| direct-air-capture | co2 stored bus + store, co2 atmosphere bus | PASS |  |
| aviation | kerosene for aviation loads (oil bus) | PASS |  |
| shipping | shipping oil (and/or H2) loads | PASS |  |
| behind-the-meter-der | LV distribution buses + grid links | PASS |  |
| rooftop-distributed-solar | solar rooftop generators (LV) | PASS |  |
| behind-the-meter-der | home battery stores (LV) | PASS |  |
| district-heating | urban central heat present (config potential*progress drives DH; CSV 'current' all-zero) | PASS |  |
| hydrogen-storage-salt-caverns | EXPECTED ABSENT: underground H2 cavern store (no MX cavern row); tank storage instead | PASS |  |

46/46 checks pass

## QA appendix

`recipes/_qa/check_recipes.py` — **91/91 recipes pass**: YAML shape per
RECIPE.schema.yaml, kebab-case ids matching filenames, exactly one pypsa-earth
model section with the exact version anchor, every provenance `file:symbol`
with the symbol verified verbatim in the referenced repo file (no line
numbers anywhere), every lever key resolved as a dot-path in
`config.default.yaml`, boundary rungs in L0–L5 with `where` anchors for L2+,
no verification fields.

Regenerate the index with `python recipes/_qa/generate_index.py` after any
recipe change; re-run both QA scripts before trusting an edited book.
