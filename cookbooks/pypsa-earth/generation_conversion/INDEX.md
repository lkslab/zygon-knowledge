# PyPSA-Earth recipe book — index

One modelling recipe per technology topic, extracted per the contract in
`enderpearl/claude_instructions/recipes/` (EXTRACTION.md + RECIPE.schema.yaml).
Every claim carries `file:symbol` provenance; version anchor: commit
`8435f4c8` (2026-07-08). *Entry rung* = the lowest rung on the recipe's
boundary ladder (L0 = flip a config key … L5 = bespoke Python). For
"not covered" topics the entry rung is marked *(proxy)*: the model has
no first-class representation of the tech, but its cheapest crude
approximation needs only that rung (e.g. floating wind ≈ relax
offwind-dc max_depth at L1, at fixed-bottom costs); the recipe's
boundary ladder gives the proper implementation rung.
Runtime validation against coarse Mexico networks: see `VALIDATION.md`.

## Supply — variable renewables

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Utility-scale solar PV | [`utility-scale-solar-pv`](utility-scale-solar-pv.yaml) | covered | L0 |
| Onshore wind | [`onshore-wind`](onshore-wind.yaml) | covered | L0 |
| Offshore wind | [`offshore-wind`](offshore-wind.yaml) | covered | L0 |
| Rooftop / distributed solar | [`rooftop-distributed-solar`](rooftop-distributed-solar.yaml) | covered | L0 |
| Concentrated solar power (CSP) | [`concentrated-solar-power`](concentrated-solar-power.yaml) | covered | L0 |
| Floating offshore wind | [`floating-offshore-wind`](floating-offshore-wind.yaml) | not covered | L1 (proxy) |
| Floating solar | [`floating-solar`](floating-solar.yaml) | not covered | L1 (proxy) |
| Conventional hydropower | [`conventional-hydropower`](conventional-hydropower.yaml) | covered | L0 |

## Supply — firm / emerging

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Run-of-river hydro | [`run-of-river-hydro`](run-of-river-hydro.yaml) | covered | L0 |
| Small modular reactors (SMR) | [`small-modular-reactors`](small-modular-reactors.yaml) | not covered | L1 (proxy) |
| Conventional nuclear | [`conventional-nuclear`](conventional-nuclear.yaml) | covered | L0 |
| Enhanced / deep geothermal (EGS) | [`enhanced-geothermal`](enhanced-geothermal.yaml) | not covered | L1 (proxy) |
| Geothermal (conventional) | [`geothermal-conventional`](geothermal-conventional.yaml) | covered | L0 |
| Nuclear fusion (emerging) | [`nuclear-fusion`](nuclear-fusion.yaml) | covered | L1 |

## Conventional & fossil (pypsa-eur parity sweep)

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Gas power plants (OCGT / CCGT) | [`gas-power-plants`](gas-power-plants.yaml) | covered | L0 |
| Coal and lignite power plants | [`coal-power-plants`](coal-power-plants.yaml) | covered | L0 |
| Oil-fired power plants (HFO/diesel steam and gensets) | [`oil-power-plants`](oil-power-plants.yaml) | covered | L0 |
| Combined heat and power (CHP) plants | [`combined-heat-and-power`](combined-heat-and-power.yaml) | covered | L0 |
| Waste-to-energy (MSW incineration / waste CHP) | [`waste-to-energy`](waste-to-energy.yaml) | not covered | L1 (proxy) |
| Fossil-fuel boilers for heating (gas and oil boilers) | [`fossil-fuel-boilers`](fossil-fuel-boilers.yaml) | covered | L0 |
| Fossil fuel supply chains (oil, natural gas, coal) | [`fossil-fuel-supply`](fossil-fuel-supply.yaml) | covered | L0 |
| Natural gas transmission network (pipelines, clustering, H2 repurposing) | [`natural-gas-pipelines`](natural-gas-pipelines.yaml) | covered | L0 |
| Green energy imports (H2, ammonia, methanol, e-fuels from abroad) | [`green-energy-imports`](green-energy-imports.yaml) | not covered | L0 (proxy) |

## Grid & interconnection

| topic | slug | coverage | entry rung |
|---|---|---|---|
| High-voltage transmission lines | [`hv-transmission-lines`](hv-transmission-lines.yaml) | covered | L0 |
| HVDC interconnectors | [`hvdc-interconnectors`](hvdc-interconnectors.yaml) | covered | L0 |
| Ultra-high-voltage (UHV) DC | [`uhv-dc`](uhv-dc.yaml) | not covered | L0 (proxy) |
| Grid-forming inverters | [`grid-forming-inverters`](grid-forming-inverters.yaml) | not covered | L0 (proxy) |
| Synchronous condensers | [`synchronous-condensers`](synchronous-condensers.yaml) | not covered | L3 (proxy) |
| Dynamic line rating / FACTS | [`dynamic-line-rating-facts`](dynamic-line-rating-facts.yaml) | not covered | L0 (proxy) |
| Solar mini-grids | [`solar-mini-grids`](solar-mini-grids.yaml) | not covered | L0 (proxy) |
| Standalone solar home systems | [`solar-home-systems`](solar-home-systems.yaml) | not covered | L0 (proxy) |
| Smart meters | [`smart-meters`](smart-meters.yaml) | not covered | L0 (proxy) |

## Storage

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Grid-scale batteries (Li-ion) | [`grid-scale-batteries`](grid-scale-batteries.yaml) | covered | L0 |
| Long-duration storage (LDES) | [`long-duration-storage`](long-duration-storage.yaml) | covered | L0 |
| Pumped hydro storage | [`pumped-hydro-storage`](pumped-hydro-storage.yaml) | covered | L0 |
| Thermal storage | [`thermal-storage`](thermal-storage.yaml) | covered | L0 |
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
| Battery electric cars | [`battery-electric-cars`](battery-electric-cars.yaml) | covered | L0 |
| Electric heavy trucks | [`electric-heavy-trucks`](electric-heavy-trucks.yaml) | not covered | L1 (proxy) |
| Smart EV chargers | [`smart-ev-chargers`](smart-ev-chargers.yaml) | covered | L0 |
| Vehicle-to-grid (V2G) | [`vehicle-to-grid`](vehicle-to-grid.yaml) | covered | L0 |
| Electric buses | [`electric-buses`](electric-buses.yaml) | not covered | L1 (proxy) |
| Rail electrification | [`rail-electrification`](rail-electrification.yaml) | covered | L0 |
| Overhead-catenary trucks (eHighway) | [`catenary-trucks`](catenary-trucks.yaml) | not covered | L1 (proxy) |
| Hydrogen fuel-cell trucks | [`hydrogen-fuel-cell-trucks`](hydrogen-fuel-cell-trucks.yaml) | covered | L1 |
| Electric ferries / short-sea shipping | [`electric-ferries`](electric-ferries.yaml) | not covered | L2 (proxy) |
| Ammonia-fuelled ships | [`ammonia-ships`](ammonia-ships.yaml) | covered | L2 |
| Methanol-fuelled ships | [`methanol-ships`](methanol-ships.yaml) | not covered | L0 (proxy) |
| Hydrogen aircraft (emerging) | [`hydrogen-aircraft`](hydrogen-aircraft.yaml) | not covered | L0 (proxy) |

## Buildings & low-temperature heat

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Air-source heat pumps | [`air-source-heat-pumps`](air-source-heat-pumps.yaml) | covered | L0 |
| Ground-source heat pumps | [`ground-source-heat-pumps`](ground-source-heat-pumps.yaml) | covered | L0 |
| Heat-pump water heaters | [`heat-pump-water-heaters`](heat-pump-water-heaters.yaml) | covered | L1 |
| Building envelope retrofit / insulation | [`building-retrofit`](building-retrofit.yaml) | covered | L0 |
| District heating networks | [`district-heating`](district-heating.yaml) | covered | L1 |
| Solar thermal (water/heat) | [`solar-thermal`](solar-thermal.yaml) | covered | L0 |
| Induction / electric cooking | [`electric-cooking`](electric-cooking.yaml) | covered | L0 |
| Clean cookstoves | [`clean-cookstoves`](clean-cookstoves.yaml) | covered | L2 |
| Electric resistance heating | [`electric-resistance-heating`](electric-resistance-heating.yaml) | covered | L0 |

## Hydrogen & low-carbon fuels

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Electrolysers | [`electrolysers`](electrolysers.yaml) | covered | L0 |
| Green hydrogen | [`green-hydrogen`](green-hydrogen.yaml) | covered | L0 |
| Green ammonia | [`green-ammonia`](green-ammonia.yaml) | covered | L0 |
| Blue hydrogen | [`blue-hydrogen`](blue-hydrogen.yaml) | covered | L0 |
| Hydrogen pipelines | [`hydrogen-pipelines`](hydrogen-pipelines.yaml) | covered | L0 |
| E-methanol | [`e-methanol`](e-methanol.yaml) | covered | L4 |
| E-kerosene / sustainable aviation fuel | [`e-kerosene-saf`](e-kerosene-saf.yaml) | covered | L0 |
| E-diesel (Fischer-Tropsch) | [`e-diesel-fischer-tropsch`](e-diesel-fischer-tropsch.yaml) | covered | L0 |
| Synthetic natural gas (e-SNG) | [`e-sng`](e-sng.yaml) | covered | L0 |
| Stationary fuel cells | [`stationary-fuel-cells`](stationary-fuel-cells.yaml) | covered | L0 |
| Advanced biofuels | [`advanced-biofuels`](advanced-biofuels.yaml) | covered | L0 |

## Industry (hard-to-abate)

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Electric arc furnace | [`electric-arc-furnace`](electric-arc-furnace.yaml) | covered | L0 |
| H2-DRI (hydrogen steel) | [`h2-dri-steel`](h2-dri-steel.yaml) | covered | L0 |
| Industrial high-temperature heat pumps | [`industrial-heat-pumps`](industrial-heat-pumps.yaml) | covered | L0 |
| Electric boilers | [`electric-boilers`](electric-boilers.yaml) | covered | L0 |
| Electric industrial process heat | [`electric-process-heat`](electric-process-heat.yaml) | covered | L2 |
| Low-clinker / alternative cement | [`low-clinker-cement`](low-clinker-cement.yaml) | covered | L1 |
| Inert-anode aluminium | [`inert-anode-aluminium`](inert-anode-aluminium.yaml) | covered | L2 |
| Green / electrolytic chemicals | [`electrolytic-chemicals`](electrolytic-chemicals.yaml) | covered | L0 |
| Mechanical vapour recompression | [`mechanical-vapour-recompression`](mechanical-vapour-recompression.yaml) | covered | L3 |
| Waste-heat recovery | [`waste-heat-recovery`](waste-heat-recovery.yaml) | covered | L2 |
| Carbon capture (industrial CCS) | [`industrial-ccs`](industrial-ccs.yaml) | covered | L0 |

## Bioenergy, waste & agriculture

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Biomass / bioenergy | [`biomass-bioenergy`](biomass-bioenergy.yaml) | covered | L0 |
| Biogas / anaerobic digestion | [`biogas-anaerobic-digestion`](biogas-anaerobic-digestion.yaml) | covered | L0 |
| Landfill-gas capture | [`landfill-gas`](landfill-gas.yaml) | covered | L1 |
| Electric farm / construction machinery | [`electric-farm-machinery`](electric-farm-machinery.yaml) | covered | L0 |

## Carbon removal (CDR)

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Direct air capture (DACCS) | [`direct-air-capture`](direct-air-capture.yaml) | covered | L0 |
| Bioenergy with CCS (BECCS) | [`beccs`](beccs.yaml) | covered | L0 |
| Biochar | [`biochar`](biochar.yaml) | covered | L5 |
| Enhanced rock weathering | [`enhanced-rock-weathering`](enhanced-rock-weathering.yaml) | covered | L2 |
| Ocean-based CDR | [`ocean-cdr`](ocean-cdr.yaml) | covered | L2 |

## Flexibility & cross-cutting

| topic | slug | coverage | entry rung |
|---|---|---|---|
| Virtual power plants (VPP) | [`virtual-power-plants`](virtual-power-plants.yaml) | covered | L0 |
| Behind-the-meter DER | [`behind-the-meter-der`](behind-the-meter-der.yaml) | covered | L0 |
| Desalination (flexible load) | [`desalination-flexible-load`](desalination-flexible-load.yaml) | covered | L3 |
| Methane leak detection / abatement | [`methane-abatement`](methane-abatement.yaml) | covered | L0 |
| Tidal / wave (emerging) | [`tidal-wave`](tidal-wave.yaml) | covered | L3 |
