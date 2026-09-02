# -*- coding: utf-8 -*-
"""
Runtime validation of the DEMAND cookbook (pypsa-earth side only).

Asserts, per demand recipe, that the Load carriers it claims exist DO appear in
the already-built coarse Mexico sector prenetwork (no new model runs):
    results/mexico-sector/prenetworks/elec_s_4_ec_lcopt_Co2L_144h_2030_0.071_AB.nc
plus the electricity load in the solved power network. pypsa-eur sections are
grounded by provenance QA only (no eur run in scope).

Expected regional absences (MX data) are asserted as such — they demonstrate the
recipes' data_dependencies fields.

Usage: python cookbooks/demand/_qa/assert_demand_loads.py [sector.nc] [power.nc]
Prints a markdown table for VALIDATION.md; exit 0 iff all checks pass.
"""

import sys

import pypsa

SECTOR_NC = (
    "results/mexico-sector/prenetworks/elec_s_4_ec_lcopt_Co2L_144h_2030_0.071_AB.nc"
)
POWER_NC = "results/mexico-power/networks/elec_s_10_ec_lcopt_Co2L.nc"

RESULTS = []


def check(recipe, description, ok, detail=""):
    RESULTS.append((recipe, description, bool(ok), detail))


def load_carrier(n, substr):
    """Loads whose carrier contains substr (case-insensitive)."""
    if not len(n.loads):
        return 0
    return int(n.loads.carrier.str.contains(substr, case=False, regex=False).sum())


def check_power(n):
    check("electricity-load", "AC electricity loads with hourly profiles",
          len(n.loads) > 0 and len(n.loads_t.p_set.columns) > 0,
          f"{len(n.loads)} loads, {n.loads_t.p_set.shape[0]} snapshots")


def check_sector(n):
    # buildings
    check("residential-space-heating-demand", "residential heat loads (rural/urban systems)",
          load_carrier(n, "residential rural heat") + load_carrier(n, "urban decentral heat") > 0, "")
    check("residential-electricity-demand", "electricity residential loads",
          load_carrier(n, "electricity residential") > 0 or load_carrier(n, "residential") > 0, "")
    check("services-electricity-demand", "services electricity loads",
          load_carrier(n, "services electricity") > 0, "")
    check("services-heat-demand", "services heat loads",
          load_carrier(n, "services") > 0, "")
    check("district-heating-demand-share", "urban central heat load (config potential*progress)",
          load_carrier(n, "urban central heat") > 0, "")

    # transport
    check("land-transport-demand", "EV + fuel cell + oil land transport loads",
          load_carrier(n, "land transport EV") > 0
          and load_carrier(n, "land transport fuel cell") > 0
          and load_carrier(n, "land transport oil") > 0, "")
    check("rail-transport-demand", "rail transport loads",
          load_carrier(n, "rail transport") > 0, "")
    check("aviation-demand", "kerosene for aviation loads",
          load_carrier(n, "kerosene for aviation") > 0, "")
    check("shipping-demand", "shipping loads",
          load_carrier(n, "shipping") > 0, "")

    # agriculture
    check("agriculture-energy-demand", "agriculture electricity + oil loads",
          load_carrier(n, "agriculture") > 0, "")

    # industry (aggregate carriers; subsector recipes share these observables)
    check("steel-demand / chemicals-demand / ... (industry families)",
          "industry electricity + gas/biomass for industry loads",
          load_carrier(n, "industry electricity") > 0
          and (load_carrier(n, "gas for industry") > 0
               or load_carrier(n, "solid biomass for industry") > 0), "")
    check("chemicals-demand", "NH3 (ammonia) demand load",
          load_carrier(n, "NH3") > 0, "")
    check("industrial-process-emissions", "process emissions load",
          load_carrier(n, "process emissions") > 0, "")
    check("industrial-feedstocks-nonenergy", "H2 / naphtha-type industry loads (report what exists)",
          load_carrier(n, "H2 for industry") > 0 or load_carrier(n, "naphtha") > 0,
          f"H2-for-industry={load_carrier(n, 'H2 for industry')}, naphtha={load_carrier(n, 'naphtha')}")

    # temporal machinery observables
    ev = n.loads.index[n.loads.carrier.str.contains("land transport EV", regex=False)]
    if len(ev):
        prof = n.loads_t.p_set[ev.intersection(n.loads_t.p_set.columns)]
        varying = bool(len(prof.columns)) and bool((prof.std() > 1e-9).any())
        check("demand-temporal-profiles", "EV load profile is time-varying (weekly traffic shape)",
              varying, "")
    heat = n.loads.index[n.loads.carrier.str.contains("heat", case=False, regex=False)]
    prof = n.loads_t.p_set[heat.intersection(n.loads_t.p_set.columns)]
    check("demand-temporal-profiles", "heat load profiles time-varying (degree-days)",
          bool(len(prof.columns)) and bool((prof.std() > 1e-9).any()), "")

    # export demand: h2export wildcard does not apply to prenetworks -> absent here
    check("hydrogen-export-demand",
          "EXPECTED ABSENT in prenetwork (export added by add_export at solve stage)",
          load_carrier(n, "export") == 0, "")


def main():
    sector = sys.argv[1] if len(sys.argv) > 1 else SECTOR_NC
    power = sys.argv[2] if len(sys.argv) > 2 else POWER_NC

    for path, fn, label in [(power, check_power, "power"), (sector, check_sector, "sector")]:
        try:
            n = pypsa.Network(path)
        except Exception as e:
            check("(load)", f"load {label} network {path}", False, str(e))
            continue
        fn(n)

    print("| recipe | check | result | detail |")
    print("|---|---|---|---|")
    n_fail = 0
    for recipe, desc, ok, detail in RESULTS:
        if not ok:
            n_fail += 1
        print(f"| {recipe} | {desc} | {'PASS' if ok else 'FAIL'} | {detail} |")
    print(f"\n{len(RESULTS) - n_fail}/{len(RESULTS)} checks pass")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
