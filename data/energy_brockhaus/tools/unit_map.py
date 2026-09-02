#!/usr/bin/env python3
"""The v1 -> v2 unit migration table. Authored by hand, one entry per observed
string. Read by migrate_v2.py --split-units.

Deliberately a literal dict, not a set of rules. Every one of the 155 unit
strings observed in targets.csv v1 appears here exactly once and was decided
individually. A regex over "% ethanol in gasoline (max ceiling)" would map it to
the same bucket as "% ethanol in gasoline (volume)" -- one is a cap and the
other a blend level, and the difference is the whole point of the row.

  key   -- the v1 `unit` string, verbatim
  value -- (unit, basis, scope_note)
             unit       closed vocabulary, pure physical dimension
             basis      closed vocabulary, the denominator; "" for absolutes
             scope_note free text; never grouped on, never parsed

QUALITATIVE lists the strings whose rows are not numeric targets at all --
policy statements, monetary flows, credit instruments, counts of objects that
carry no energy meaning. Those rows leave targets.csv rather than being coerced
into a number. A qualitative target that pretends to be a number is worse than
no row, for the same reason MAINTAINER.md says an unsourced row is worse than a
missing one.
"""

# --- the closed vocabularies (migrate_v2.py applies them, check_registry.py
# --- enforces them; this module is the single definition of both) -----------

UNITS = {
    "GW", "MW", "GWh", "MWh", "TWh", "PJ",             # power / energy stock
    "TWh/yr", "PJ/yr",                                  # energy flow
    "MtCO2eq", "MtCO2", "MtCO2/yr",                     # emissions
    "pct",                                              # percentage; basis says of what
    "Mt/yr", "kt/yr", "t/yr",                           # mass flow
    "bcm/yr", "Smc/h", "Ggal/yr", "kb/d", "bbl/d",      # volume flow
    "count",                                            # discrete; noun in scope_note
    "ratio",                                            # dimensionless multiplier
}

# `basis` is the denominator that makes two percentages comparable. Only
# meaningful for pct and ratio; "" for absolute units, and "" for a percentage
# whose base the source never stated (which is honest, not a gap to guess at).
BASIS = {
    "", "gross_final_energy", "electricity_generation", "electricity_consumption",
    "primary_energy", "installed_capacity", "baseline_year", "present_level",
    "transport_energy", "fuel_volume", "jet_fuel_demand", "gas_supply",
    "population", "households", "ghg_intensity", "vehicle_sales", "heat_supply",
}

# Rows that are not numeric energy targets. Parked, then re-homed into
# regulation.csv (where non-numeric policy belongs) or dropped.
QUALITATIVE = {
    "no-new-coal",                                    # a policy stance, not a value
    "large-scale biogas facilities (+ ~50 million household digesters)",
    "GW WtE incineration (qualitative steady-development goal)",  # says so itself
    "% ethanol blend (E10) nationwide (stalled)",     # stalled => not a target
    "solar_kits",                                     # count of kits, not energy
    "hectares_land_allocated",                        # land, not energy
    "communities",                                    # count of communities
    "million CBIOs (decarbonization credits)",        # tradable credit instrument
    "billion RINs",                                   # tradable credit instrument
    "USD bn/yr (LNG exports)",                        # monetary flow
    "USD/kg",                                         # a price, not a target
    "% of global market",                             # market share, not energy
    "tonnes cumulative SAF by 2025",                  # cumulative-to-date, not a rate
    "bcm routine flaring",                            # flaring volume, not a target
    "Mm3/d exports",                                  # export volume, not a target
}

UNIT_MAP = {
    # ---- power / capacity -------------------------------------------------
    "GW": ("GW", "", ""),
    "MW": ("MW", "", ""),
    "GW_el": ("GW", "", "electrical"),
    "GW_electrolysis": ("GW", "", "electrolyser input"),
    "GWp": ("GW", "", "peak (DC)"),
    "MW_electrolyser": ("MW", "", "electrolyser"),
    "GW flexible biogas capacity": ("GW", "", "flexible biogas"),
    "GW (new bioenergy capacity 2025-2034)": ("GW", "", "new bioenergy capacity 2025-2034"),
    "MW/yr (auction volume, 2026-2028)": ("MW", "", "annual auction volume 2026-2028"),

    # ---- energy -----------------------------------------------------------
    "TWh": ("TWh", "", ""),
    "GWh": ("GWh", "", ""),
    "MWh": ("MWh", "", ""),
    "PJ": ("PJ", "", ""),
    "TWh/yr": ("TWh/yr", "", ""),
    "TWh_per_year": ("TWh/yr", "", ""),
    "TWh/yr biogas": ("TWh/yr", "", "biogas"),
    "TWh/yr biogas to road transport": ("TWh/yr", "", "biogas to road transport"),
    "TWh/yr (biogas+biomethane)": ("TWh/yr", "", "biogas + biomethane"),
    "TWh/yr (biogas)": ("TWh/yr", "", "biogas"),
    "PJ_per_year": ("PJ/yr", "", ""),
    "PJ/yr renewable gas": ("PJ/yr", "", "renewable gas"),

    # ---- emissions / CO2 --------------------------------------------------
    "MtCO2eq": ("MtCO2eq", "", ""),
    "MtCO2": ("MtCO2", "", ""),
    "MtCO2/yr": ("MtCO2/yr", "", ""),
    "Mt CO2/yr": ("MtCO2/yr", "", ""),

    # ---- mass / volume flows ---------------------------------------------
    "Mt/yr": ("Mt/yr", "", ""),
    "Mt/year": ("Mt/yr", "", ""),
    "Mtpa": ("Mt/yr", "", ""),
    "MMT/year": ("Mt/yr", "", ""),
    "Mtpa LNG": ("Mt/yr", "", "LNG"),
    "Mt/yr green H2": ("Mt/yr", "", "green hydrogen"),
    "Mt_renewable_H2_imported": ("Mt/yr", "", "renewable hydrogen imported"),
    "Mt biomass/year (co-firing demand at 10% blend)":
        ("Mt/yr", "", "biomass co-firing demand at 10% blend"),
    "kt/yr": ("kt/yr", "", ""),
    "kt/yr H2": ("kt/yr", "", "hydrogen"),
    "t/yr": ("t/yr", "", ""),
    "tonnes/yr": ("t/yr", "", ""),
    "bcm/yr": ("bcm/yr", "", ""),
    "bcm/yr (potential by 2026)": ("bcm/yr", "", "potential by 2026"),
    "bcm/yr green gas (biomethane)": ("bcm/yr", "", "green gas (biomethane)"),
    "Smc/h": ("Smc/h", "", ""),
    "Smc/h (biomethane upgrading capacity, current)":
        ("Smc/h", "", "biomethane upgrading, current"),
    "billion gal/yr": ("Ggal/yr", "", ""),
    "kb/d": ("kb/d", "", ""),
    "bbl/day": ("bbl/d", "", ""),

    # ---- counts -----------------------------------------------------------
    "units": ("count", "", "units"),
    "reactor-equivalents": ("count", "", "reactor equivalents"),
    "reactor units": ("count", "", "reactor units"),
    "vehicles": ("count", "", "vehicles"),
    "connections": ("count", "", "grid connections"),
    "CBG plants": ("count", "", "compressed-biogas plants"),

    # ---- dimensionless ratios --------------------------------------------
    "x_baseline": ("ratio", "present_level", "multiple of baseline"),
    "factor_vs_present": ("ratio", "present_level", ""),

    # ---- percentages: unstated base --------------------------------------
    "%": ("pct", "", ""),

    # ---- percentages: vs a baseline year ---------------------------------
    "%_vs_baseline": ("pct", "baseline_year", ""),
    "percent_increase": ("pct", "present_level", "increase vs present"),

    # ---- percentages: of final / primary energy --------------------------
    "%_gross_final_energy": ("pct", "gross_final_energy", ""),
    "%_of_final_energy": ("pct", "gross_final_energy", ""),
    "%_of_energy": ("pct", "gross_final_energy", ""),
    "% of energy mix": ("pct", "gross_final_energy", ""),
    "% of primary energy": ("pct", "primary_energy", ""),

    # ---- percentages: of electricity generation --------------------------
    "% of electricity generation": ("pct", "electricity_generation", ""),
    "% of electricity generation (non-hydro renewables incl. biomass)":
        ("pct", "electricity_generation", "non-hydro renewables incl. biomass"),
    "% of power generation": ("pct", "electricity_generation", ""),
    "% of generation": ("pct", "electricity_generation", ""),
    "% of electricity output": ("pct", "electricity_generation", ""),
    "% of daily power generation": ("pct", "electricity_generation", "daily"),
    "%_generation_mix": ("pct", "electricity_generation", ""),
    "%_electricity_mix": ("pct", "electricity_generation", ""),
    "% of power mix": ("pct", "electricity_generation", ""),
    "% of fuel mix": ("pct", "electricity_generation", "fuel mix"),
    "%_of_electricity": ("pct", "electricity_generation", ""),
    "% of electricity": ("pct", "electricity_generation", ""),
    "%_electricity": ("pct", "electricity_generation", ""),
    "% biomass co-firing in coal TPPs (energy)":
        ("pct", "electricity_generation", "biomass co-firing in coal thermal plants"),

    # ---- percentages: of electricity consumption -------------------------
    "%_of_electricity_consumption": ("pct", "electricity_consumption", ""),
    "%_of_demand": ("pct", "electricity_consumption", ""),

    # ---- percentages: of installed capacity ------------------------------
    "%_installed_capacity": ("pct", "installed_capacity", ""),
    "% installed capacity": ("pct", "installed_capacity", ""),
    "% of installed capacity": ("pct", "installed_capacity", ""),
    "%_new_capacity": ("pct", "installed_capacity", "new capacity"),

    # ---- percentages: of population / households (access, SDG7) ----------
    "%_population_access": ("pct", "population", "electricity access"),
    "% population access": ("pct", "population", "access"),
    "% of population with electricity access": ("pct", "population", "electricity access"),
    "% of population with access": ("pct", "population", "access"),
    "% access": ("pct", "population", "access"),
    "%_access": ("pct", "population", "access"),
    "% population": ("pct", "population", ""),
    "%_of_population": ("pct", "population", ""),
    "% of population": ("pct", "population", ""),
    "%_per_year_electrification_rate": ("pct", "population", "per-year electrification rate"),
    "%_new_connections_by_2030": ("pct", "population", "new connections by 2030"),
    "%_of_electricity_consumers": ("pct", "population", "of electricity consumers"),
    "%_households": ("pct", "households", ""),
    "% of households": ("pct", "households", ""),
    "% households (clean cooking)": ("pct", "households", "clean cooking"),

    # ---- percentages: GHG intensity --------------------------------------
    "% carbon-intensity reduction": ("pct", "ghg_intensity", ""),
    "percent_GHG_intensity_reduction": ("pct", "ghg_intensity", ""),
    "% GHG reduction": ("pct", "ghg_intensity", ""),
    "% GHG reduction (transport fuels)": ("pct", "ghg_intensity", "transport fuels"),
    "% GHG-intensity reduction of road transport fuels":
        ("pct", "ghg_intensity", "road transport fuels"),
    "% GHG reduction of transport fuel deliveries (vs 2010)":
        ("pct", "ghg_intensity", "transport fuel deliveries, vs 2010"),
    "% emissions reduction via biomethane (start)":
        ("pct", "ghg_intensity", "via biomethane, initial step"),
    "% GHG reduction in aviation via SAF (start, to 10% by 2037)":
        ("pct", "ghg_intensity", "aviation via SAF, initial step rising to 10% by 2037"),

    # ---- percentages: fuel blends by volume ------------------------------
    "% biodiesel (FAME) blend in diesel (volume)":
        ("pct", "fuel_volume", "FAME biodiesel in diesel"),
    "% biodiesel in diesel (volume)": ("pct", "fuel_volume", "biodiesel in diesel"),
    "% ethanol in gasoline (volume)": ("pct", "fuel_volume", "ethanol in gasoline"),
    "% ethanol in gasoline (max ceiling)":
        ("pct", "fuel_volume", "ethanol in gasoline, maximum ceiling"),
    "% ethanol in petrol (volume)": ("pct", "fuel_volume", "ethanol in petrol"),
    "% bioethanol blend in gasoline (volume)":
        ("pct", "fuel_volume", "bioethanol in gasoline"),
    "% blend by volume": ("pct", "fuel_volume", ""),
    "% of fuel by volume": ("pct", "fuel_volume", ""),
    "% of road/NRMM fuel by volume":
        ("pct", "fuel_volume", "road and non-road mobile machinery"),
    "% CBG in CNG/PNG (volume)": ("pct", "fuel_volume", "compressed biogas in CNG/PNG"),

    # ---- percentages: of transport energy --------------------------------
    "% renewable fuels in road transport (energy)": ("pct", "transport_energy", "road transport"),
    "% energy in transport fuels": ("pct", "transport_energy", ""),
    "% energy in transport (advanced biofuels)":
        ("pct", "transport_energy", "advanced biofuels"),
    "% advanced biofuels sub-target (energy)":
        ("pct", "transport_energy", "advanced biofuels sub-target"),
    "% energy (petrol)": ("pct", "transport_energy", "petrol"),
    "% biofuel blending (energy content)": ("pct", "transport_energy", "energy content"),
    "% advanced biofuels (energy content)":
        ("pct", "transport_energy", "advanced biofuels, energy content"),
    "% advanced biofuels + RFNBO in transport energy":
        ("pct", "transport_energy", "advanced biofuels + RFNBO"),
    "% renewable energy in transport fuel deliveries":
        ("pct", "transport_energy", "fuel deliveries"),
    "% advanced biofuels in transport (energy share)":
        ("pct", "transport_energy", "advanced biofuels"),
    "% renewable energy in transport": ("pct", "transport_energy", ""),

    # ---- percentages: of jet fuel ----------------------------------------
    "% of total UK jet fuel demand": ("pct", "jet_fuel_demand", ""),
    "% of jet fuel demand (PtL sub-target)":
        ("pct", "jet_fuel_demand", "power-to-liquid sub-target"),
    "% of jet fuel": ("pct", "jet_fuel_demand", ""),
    "% SAF blending (expected)": ("pct", "jet_fuel_demand", "SAF, expected"),
    "% SAF share at EU airports": ("pct", "jet_fuel_demand", "at EU airports"),

    # ---- percentages: of gas supply --------------------------------------
    "% green gas blended in gas supply (indicative 2030)":
        ("pct", "gas_supply", "green gas, indicative"),
    "% biomethane in gas market (2030 step)": ("pct", "gas_supply", "biomethane, 2030 step"),
    "% of gas-grid consumption green gas": ("pct", "gas_supply", "green gas"),
    "% of gas-grid throughput biomethane": ("pct", "gas_supply", "biomethane"),
    "% of gas consumption": ("pct", "gas_supply", ""),

    # ---- percentages: heat -----------------------------------------------
    "% renewable energy in new heating systems": ("pct", "heat_supply", "new heating systems"),
    "percent_share_district_heat": ("pct", "heat_supply", "district heat share"),

    # ---- percentages: vehicles -------------------------------------------
    "% of private passenger vehicle sales": ("pct", "vehicle_sales", "private passenger"),

    # ---- percentages: base named only in the note ------------------------
    "percent_of_industrial_H2": ("pct", "", "of industrial hydrogen demand"),
    "%_of_EU_clean_hydrogen": ("pct", "", "of EU clean hydrogen production"),
}

# Self-consistency: a string cannot be both migrated and parked, and every
# target of the map must be inside the closed vocabularies.
assert not (set(UNIT_MAP) & QUALITATIVE), sorted(set(UNIT_MAP) & QUALITATIVE)
assert not {u for u, _, _ in UNIT_MAP.values()} - UNITS, \
    sorted({u for u, _, _ in UNIT_MAP.values()} - UNITS)
assert not {b for _, b, _ in UNIT_MAP.values()} - BASIS, \
    sorted({b for _, b, _ in UNIT_MAP.values()} - BASIS)
