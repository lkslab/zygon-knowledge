# PyPSA-Eur recipe book — index

One modelling recipe per technology topic, extracted per the contract in
`enderpearl/claude_instructions/recipes/` (EXTRACTION.md + RECIPE.schema.yaml).
Every claim carries `file:symbol` provenance; version anchor: commit
`849c8858` (2026-07-23). *Entry rung* = the lowest rung on the recipe's
boundary ladder (L0 = flip a config key … L5 = bespoke Python). For
"not covered" topics the entry rung is marked *(proxy)*: the model has
no first-class representation of the tech, but its cheapest crude
approximation needs only that rung; the recipe's boundary ladder gives
the proper implementation rung. The topic universe mirrors the
pypsa-earth book (same 100 slugs) plus a pypsa-eur-only family.

## Supply — variable renewables

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Utility-scale solar PV | [`utility-scale-solar-pv`](utility-scale-solar-pv.yaml) | covered | L0 |
| Onshore wind | [`onshore-wind`](onshore-wind.yaml) | covered | L0 |
| Offshore wind (fixed-bottom) | [`offshore-wind`](offshore-wind.yaml) | covered | L0 |
| Rooftop / distributed solar | [`rooftop-distributed-solar`](rooftop-distributed-solar.yaml) | covered | L0 |
| Concentrated solar power (CSP) | [`concentrated-solar-power`](concentrated-solar-power.yaml) | not covered | L0 (proxy) |
| Floating offshore wind | [`floating-offshore-wind`](floating-offshore-wind.yaml) | covered | L0 |
| Floating solar | [`floating-solar`](floating-solar.yaml) | not covered | L1 (proxy) |
| Conventional hydropower | [`conventional-hydropower`](conventional-hydropower.yaml) | covered | L0 |

## Supply — firm / emerging

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Run-of-river hydro | [`run-of-river-hydro`](run-of-river-hydro.yaml) | covered | L0 |
| Small modular reactors (SMR) | [`small-modular-reactors`](small-modular-reactors.yaml) | not covered | L1 (proxy) |
| Conventional nuclear | [`conventional-nuclear`](conventional-nuclear.yaml) | covered | L0 |
| Enhanced / deep geothermal (EGS) | [`enhanced-geothermal`](enhanced-geothermal.yaml) | covered | L0 |
| Geothermal (conventional) | [`geothermal-conventional`](geothermal-conventional.yaml) | covered | L0 |
| Nuclear fusion (emerging) | [`nuclear-fusion`](nuclear-fusion.yaml) | not covered | L1 (proxy) |

## Conventional & fossil

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Gas power plants (OCGT / CCGT) | [`gas-power-plants`](gas-power-plants.yaml) | covered | L0 |
| Coal and lignite power plants | [`coal-power-plants`](coal-power-plants.yaml) | covered | L0 |
| Oil power plants | [`oil-power-plants`](oil-power-plants.yaml) | covered | L0 |
| Combined heat and power (CHP) plants | [`combined-heat-and-power`](combined-heat-and-power.yaml) | covered | L0 |
| Waste-to-energy (waste incineration, waste CHP, municipal solid waste) | [`waste-to-energy`](waste-to-energy.yaml) | covered | L0 |
| Fossil fuel boilers (gas and oil heating) | [`fossil-fuel-boilers`](fossil-fuel-boilers.yaml) | covered | L0 |
| Fossil fuel supply (gas, oil, coal, lignite commodities) | [`fossil-fuel-supply`](fossil-fuel-supply.yaml) | covered | L0 |
| Natural gas pipeline network | [`natural-gas-pipelines`](natural-gas-pipelines.yaml) | covered | L0 |
| Green energy imports (H2, ammonia, methanol, e-fuels, biomass) | [`green-energy-imports`](green-energy-imports.yaml) | covered | L0 |

## Grid & interconnection

| topic | slug | coverage | entry rung |
|---|---|---|---|
| High-voltage transmission lines | [`hv-transmission-lines`](hv-transmission-lines.yaml) | covered | L0 |
| HVDC interconnectors | [`hvdc-interconnectors`](hvdc-interconnectors.yaml) | covered | L0 |
| Ultra-high-voltage (UHV) DC | [`uhv-dc`](uhv-dc.yaml) | not covered | L0 (proxy) |
| Grid-forming inverters | [`grid-forming-inverters`](grid-forming-inverters.yaml) | not covered | L0 (proxy) |
| Synchronous condensers | [`synchronous-condensers`](synchronous-condensers.yaml) | not covered | L3 (proxy) |
| Dynamic line rating / FACTS | [`dynamic-line-rating-facts`](dynamic-line-rating-facts.yaml) | covered | L0 |
| Solar mini-grids | [`solar-mini-grids`](solar-mini-grids.yaml) | not covered | L0 (proxy) |
| Standalone solar home systems | [`solar-home-systems`](solar-home-systems.yaml) | not covered | L0 (proxy) |
| Smart meters | [`smart-meters`](smart-meters.yaml) | not covered | L0 (proxy) |

## Storage

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Grid-scale batteries (Li-ion / LFP) | [`grid-scale-batteries`](grid-scale-batteries.yaml) | covered | L0 |
| Long-duration storage (LDES) | [`long-duration-storage`](long-duration-storage.yaml) | covered | L0 |
| Pumped hydro storage | [`pumped-hydro-storage`](pumped-hydro-storage.yaml) | covered | L0 |
| Thermal storage (water tanks / pit storage) | [`thermal-storage`](thermal-storage.yaml) | covered | L0 |
| Flow batteries | [`flow-batteries`](flow-batteries.yaml) | covered | L1 |
| Sodium-ion batteries | [`sodium-ion-batteries`](sodium-ion-batteries.yaml) | covered | L1 |
| Iron-air / metal-air batteries | [`iron-air-batteries`](iron-air-batteries.yaml) | covered | L1 |
| Compressed-air storage (CAES) | [`compressed-air-storage`](compressed-air-storage.yaml) | covered | L1 |
| Liquid-air storage (LAES) | [`liquid-air-storage`](liquid-air-storage.yaml) | covered | L1 |
| Gravity storage | [`gravity-storage`](gravity-storage.yaml) | covered | L1 |
| Hydrogen storage (salt caverns) | [`hydrogen-storage-salt-caverns`](hydrogen-storage-salt-caverns.yaml) | covered | L0 |

## Transport

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Battery electric cars (passenger EVs) | [`battery-electric-cars`](battery-electric-cars.yaml) | covered | L0 |
| Battery electric heavy trucks | [`electric-heavy-trucks`](electric-heavy-trucks.yaml) | not covered | L1 (proxy) |
| Smart EV chargers (managed / flexible charging) | [`smart-ev-chargers`](smart-ev-chargers.yaml) | covered | L0 |
| Vehicle-to-grid (V2G) | [`vehicle-to-grid`](vehicle-to-grid.yaml) | covered | L0 |
| Electric buses | [`electric-buses`](electric-buses.yaml) | not covered | L1 (proxy) |
| Rail electrification | [`rail-electrification`](rail-electrification.yaml) | covered | L0 |
| Catenary trucks (electric road systems / eHighways) | [`catenary-trucks`](catenary-trucks.yaml) | not covered | L1 (proxy) |
| Hydrogen fuel cell trucks (and road vehicles) | [`hydrogen-fuel-cell-trucks`](hydrogen-fuel-cell-trucks.yaml) | covered | L1 |
| Electric ferries (battery shipping) | [`electric-ferries`](electric-ferries.yaml) | not covered | L1 (proxy) |
| Ammonia-fuelled ships | [`ammonia-ships`](ammonia-ships.yaml) | not covered | L1 (proxy) |
| Methanol-fuelled ships | [`methanol-ships`](methanol-ships.yaml) | covered | L0 |
| Hydrogen aircraft | [`hydrogen-aircraft`](hydrogen-aircraft.yaml) | not covered | L0 (proxy) |

## Buildings & low-temperature heat

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Air-source heat pumps | [`air-source-heat-pumps`](air-source-heat-pumps.yaml) | covered | L0 |
| Ground-source heat pumps | [`ground-source-heat-pumps`](ground-source-heat-pumps.yaml) | covered | L0 |
| Heat pump water heaters | [`heat-pump-water-heaters`](heat-pump-water-heaters.yaml) | covered | L0 |
| Building retrofit (insulation) | [`building-retrofit`](building-retrofit.yaml) | covered | L0 |
| District heating | [`district-heating`](district-heating.yaml) | covered | L0 |
| Solar thermal collectors | [`solar-thermal`](solar-thermal.yaml) | covered | L0 |
| Induction / electric cooking | [`electric-cooking`](electric-cooking.yaml) | covered | L0 |
| Clean cookstoves | [`clean-cookstoves`](clean-cookstoves.yaml) | covered | L1 |
| Electric resistance heating | [`electric-resistance-heating`](electric-resistance-heating.yaml) | covered | L0 |

## Hydrogen & low-carbon fuels

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Hydrogen electrolysers | [`electrolysers`](electrolysers.yaml) | covered | L0 |
| Green hydrogen (renewable-based H2 supply chain) | [`green-hydrogen`](green-hydrogen.yaml) | covered | L0 |
| Green ammonia (Haber-Bosch synthesis chain) | [`green-ammonia`](green-ammonia.yaml) | covered | L0 |
| Blue hydrogen (steam methane reforming with CCS) | [`blue-hydrogen`](blue-hydrogen.yaml) | covered | L0 |
| Hydrogen pipeline network | [`hydrogen-pipelines`](hydrogen-pipelines.yaml) | covered | L0 |
| E-methanol (power/H2 + CO2 methanol synthesis) | [`e-methanol`](e-methanol.yaml) | covered | L0 |
| E-kerosene / sustainable aviation fuel (SAF) | [`e-kerosene-saf`](e-kerosene-saf.yaml) | covered | L0 |
| E-diesel / Fischer-Tropsch synthetic fuels | [`e-diesel-fischer-tropsch`](e-diesel-fischer-tropsch.yaml) | covered | L0 |
| E-SNG / synthetic methane (Sabatier methanation) | [`e-sng`](e-sng.yaml) | covered | L0 |
| Stationary hydrogen fuel cells | [`stationary-fuel-cells`](stationary-fuel-cells.yaml) | covered | L0 |
| Advanced biofuels (BtL, electrobiofuels, BioSNG, bioH2, biogas upgrading) | [`advanced-biofuels`](advanced-biofuels.yaml) | covered | L0 |

## Industry (hard-to-abate)

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Electric arc furnace (EAF) steel | [`electric-arc-furnace`](electric-arc-furnace.yaml) | covered | L1 |
| Hydrogen direct reduced iron (H2-DRI) steel | [`h2-dri-steel`](h2-dri-steel.yaml) | covered | L1 |
| Industrial heat pumps | [`industrial-heat-pumps`](industrial-heat-pumps.yaml) | covered | L0 |
| Electric boilers | [`electric-boilers`](electric-boilers.yaml) | covered | L0 |
| Electric industrial process heat | [`electric-process-heat`](electric-process-heat.yaml) | covered | L0 |
| Low-clinker cement | [`low-clinker-cement`](low-clinker-cement.yaml) | covered | L0 |
| Inert-anode aluminium | [`inert-anode-aluminium`](inert-anode-aluminium.yaml) | covered | L0 |
| Electrolytic and electricity-based chemicals | [`electrolytic-chemicals`](electrolytic-chemicals.yaml) | covered | L0 |
| Mechanical vapour recompression | [`mechanical-vapour-recompression`](mechanical-vapour-recompression.yaml) | covered | L0 |
| Waste-heat recovery | [`waste-heat-recovery`](waste-heat-recovery.yaml) | covered | L0 |
| Industrial carbon capture (CCS/CCU in industry) | [`industrial-ccs`](industrial-ccs.yaml) | covered | L0 |

## Bioenergy, waste & agriculture

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Biomass / bioenergy (umbrella) | [`biomass-bioenergy`](biomass-bioenergy.yaml) | covered | L0 |
| Biogas / anaerobic digestion | [`biogas-anaerobic-digestion`](biogas-anaerobic-digestion.yaml) | covered | L0 |
| Landfill-gas capture | [`landfill-gas`](landfill-gas.yaml) | covered | L2 |
| Electric farm machinery | [`electric-farm-machinery`](electric-farm-machinery.yaml) | covered | L0 |

## Carbon removal (CDR)

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Direct air capture (DACCS) | [`direct-air-capture`](direct-air-capture.yaml) | covered | L0 |
| Bioenergy with CCS (BECCS) | [`beccs`](beccs.yaml) | covered | L0 |
| Biochar | [`biochar`](biochar.yaml) | covered | L2 |
| Enhanced rock weathering | [`enhanced-rock-weathering`](enhanced-rock-weathering.yaml) | covered | L2 |
| Ocean-based CDR | [`ocean-cdr`](ocean-cdr.yaml) | covered | L2 |

## Flexibility & cross-cutting

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Virtual power plants (VPP) | [`virtual-power-plants`](virtual-power-plants.yaml) | covered | L0 |
| Behind-the-meter DER | [`behind-the-meter-der`](behind-the-meter-der.yaml) | covered | L0 |
| Desalination (flexible load) | [`desalination-flexible-load`](desalination-flexible-load.yaml) | covered | L1 |
| Methane leak detection / abatement | [`methane-abatement`](methane-abatement.yaml) | covered | L0 |
| Tidal / wave (emerging) | [`tidal-wave`](tidal-wave.yaml) | covered | L3 |

## pypsa-eur additions (no earth counterpart)

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Biomass to methanol (with and without carbon capture) | [`biomass-to-methanol`](biomass-to-methanol.yaml) | covered | L0 |
| Methanol steam reforming to hydrogen (with and without carbon capture) | [`methanol-reforming`](methanol-reforming.yaml) | covered | L0 |
| Methanol-fired power plants (OCGT / CCGT / CCGT-CC / Allam) | [`methanol-to-power`](methanol-to-power.yaml) | covered | L0 |
| CO2 transport, storage and sequestration (carbon management layer) | [`co2-transport-and-sequestration`](co2-transport-and-sequestration.yaml) | covered | L0 |
| Allam cycle gas power plant (oxy-fuel with inherent CO2 capture) | [`allam-cycle`](allam-cycle.yaml) | covered | L0 |
| Aquifer thermal energy storage (ATES) | [`aquifer-thermal-storage`](aquifer-thermal-storage.yaml) | covered | L0 |
| Retrofitting gas pipelines to hydrogen | [`hydrogen-pipeline-retrofitting`](hydrogen-pipeline-retrofitting.yaml) | covered | L0 |
| Endogenous industrial process heat (industry_t) | [`industry-process-heat-endogenous`](industry-process-heat-endogenous.yaml) | covered | L0 |
| Electricity distribution grid (low-voltage layer) | [`electricity-distribution-grid`](electricity-distribution-grid.yaml) | covered | L0 |
| Transmission expansion projects (TYNDP / NEP / manual) | [`transmission-expansion-projects`](transmission-expansion-projects.yaml) | covered | L0 |
