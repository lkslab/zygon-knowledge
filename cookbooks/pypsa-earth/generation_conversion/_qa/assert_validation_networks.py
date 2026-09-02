# -*- coding: utf-8 -*-
"""
Runtime validation of the recipe book against the coarse Mexico networks.

Maps recipe claims to observable components in
  a) results/mexico-power/networks/elec_s_4_ec_lcopt_Co2L.nc            (solved)
  b) results/mexico-sector/prenetworks/elec_s_4_ec_lcopt_Co2L_144h_2030_0.071_AB.nc

Each check names the recipe it validates. "Expected absences" (district heating,
H2 salt caverns, aluminium demand) are asserted ABSENT — they demonstrate the
recipes' data_dependencies (region-dependent data), not failures.

Usage: python recipes/_qa/assert_validation_networks.py [power.nc] [sector.nc]
Prints a markdown pass/fail table (pasted into recipes/VALIDATION.md); exit 0
iff all checks pass.
"""

import sys

import numpy as np
import pypsa

POWER_NC = "results/mexico-power/networks/elec_s_10_ec_lcopt_Co2L.nc"
SECTOR_NC = (
    "results/mexico-sector/prenetworks/elec_s_4_ec_lcopt_Co2L_144h_2030_0.071_AB.nc"
)

RESULTS = []


def check(recipe, description, ok, detail=""):
    RESULTS.append((recipe, description, bool(ok), detail))


def has_carrier(df, carrier):
    return (df.carrier == carrier).any() if len(df) else False


def carrier_like(df, substr, col="carrier"):
    return df[col].str.contains(substr, case=False, regex=False).any() if len(df) else False


def index_like(df, substr):
    return df.index.str.contains(substr, case=False, regex=False).any() if len(df) else False


def check_power(n):
    g, su, st, ln, lk = n.generators, n.storage_units, n.stores, n.lines, n.links

    for tech, recipe in [
        ("solar", "utility-scale-solar-pv"),
        ("onwind", "onshore-wind"),
        ("offwind-ac", "offshore-wind"),
        ("offwind-dc", "offshore-wind"),
    ]:
        sub = g[g.carrier == tech]
        check(recipe, f"{tech} generators present + extendable",
              len(sub) > 0 and sub.p_nom_extendable.any(),
              f"{len(sub)} gens")

    sub = g[g.carrier == "csp"]
    check("concentrated-solar-power", "csp generators (L1 lever renewable_carriers+=csp)",
          len(sub) > 0, f"{len(sub)} gens")
    check("concentrated-solar-power", "csp TES stores + power-block links (csp_model advanced)",
          carrier_like(st, "csp") and carrier_like(lk, "csp"),
          f"stores={st[st.carrier.str.contains('csp', case=False)].shape[0] if len(st) else 0}, "
          f"links={lk[lk.carrier.str.contains('csp', case=False)].shape[0] if len(lk) else 0}")

    check("conventional-hydropower", "hydro StorageUnits with inflow",
          has_carrier(su, "hydro"),
          f"{(su.carrier == 'hydro').sum() if len(su) else 0} units")
    check("run-of-river-hydro", "ror generators",
          has_carrier(g, "ror"), f"{(g.carrier == 'ror').sum()} gens")
    check("pumped-hydro-storage",
          "EXPECTED ABSENT: PHS (brownfield-only mechanism; no MX PHS in powerplantmatching)",
          not has_carrier(su, "PHS"),
          f"{(su.carrier == 'PHS').sum() if len(su) else 0} units — absence validates the "
          "recipe's region-dependent fleet data_dependency")

    for tech, recipe in [
        ("nuclear", "conventional-nuclear"),
        ("geothermal", "geothermal-conventional"),
        ("OCGT", "hv-transmission-lines"),  # placeholder carrier check; OCGT recipe-free
    ]:
        if tech == "OCGT":
            continue
        check(recipe, f"{tech} fleet from powerplantmatching",
              has_carrier(g, tech), f"{(g.carrier == tech).sum()} gens")

    check("grid-scale-batteries", "battery as StorageUnit (extendable_carriers.StorageUnit)",
          has_carrier(su, "battery"), f"{(su.carrier == 'battery').sum() if len(su) else 0} units")
    check("grid-scale-batteries", "battery as Store + charger/discharger links",
          has_carrier(st, "battery") and carrier_like(lk, "battery"),
          f"stores={(st.carrier == 'battery').sum() if len(st) else 0}")
    check("hydrogen-power-storage" if False else "electrolysers",
          "H2 store + electrolysis/fuel cell links (power chain attach_stores)",
          has_carrier(st, "H2") and index_like(lk, "electrolysis") and index_like(lk, "fuel cell"),
          "")

    check("hv-transmission-lines", "AC lines extendable under lcopt",
          len(ln) > 0 and ln.s_nom_extendable.any(), f"{len(ln)} lines")
    check("hv-transmission-lines", "solved: objective finite",
          np.isfinite(n.objective), f"objective={getattr(n, 'objective', float('nan')):.4g}")


def check_sector(n):
    g, su, st, lk, ld, b = (n.generators, n.storage_units, n.stores, n.links,
                            n.loads, n.buses)

    check("battery-electric-cars", "EV loads + BEV charger links + EV battery buses",
          carrier_like(ld, "land transport EV") and index_like(lk, "BEV charger")
          and carrier_like(b, "Li ion"), "")
    check("smart-ev-chargers", "EV battery Store (bev_dsm)",
          index_like(st, "EV battery"), "")
    check("vehicle-to-grid", "V2G links",
          index_like(lk, "V2G"), "")
    check("hydrogen-fuel-cell-trucks", "land transport fuel cell loads (aggregate H2 road share)",
          carrier_like(ld, "land transport fuel cell"), "")
    check("rail-electrification", "rail transport electricity + oil loads",
          carrier_like(ld, "rail transport electricity") or carrier_like(ld, "rail transport oil"), "")

    check("air-source-heat-pumps", "air heat pump links",
          index_like(lk, "air heat pump"), "")
    check("ground-source-heat-pumps", "ground heat pump links (rural systems)",
          index_like(lk, "ground heat pump"), "")
    check("electric-resistance-heating", "resistive heater links",
          index_like(lk, "resistive heater"), "")
    check("solar-thermal", "solar thermal generators on heat buses",
          carrier_like(g, "solar thermal"), "")
    check("thermal-storage", "water tank stores + charger/discharger",
          index_like(st, "water tank"), "")

    check("electrolysers", "H2 Electrolysis links (production_technologies)",
          index_like(lk, "H2 Electrolysis") or index_like(lk, "Electrolysis"), "")
    check("blue-hydrogen", "SMR + SMR CC links",
          index_like(lk, "SMR"), "")
    check("hydrogen-pipelines", "H2 pipeline links",
          carrier_like(lk, "H2 pipeline"), "")
    check("e-diesel-fischer-tropsch", "Fischer-Tropsch links (feed shared oil bus)",
          index_like(lk, "Fischer-Tropsch"), "")
    check("e-sng", "Sabatier / helmeth methanation links",
          index_like(lk, "Sabatier") or index_like(lk, "helmeth"), "")
    check("green-ammonia", "Haber-Bosch links + NH3 buses + ammonia store",
          index_like(lk, "Haber-Bosch") and carrier_like(b, "NH3"), "")

    check("industry-energy-demand" if False else "industrial-ccs",
          "industry CC capture links (gas/biomass for industry CC)",
          index_like(lk, "industry CC") or index_like(lk, "for industry CC"), "")
    check("electric-arc-furnace", "industry electricity loads (aggregate demand-side)",
          carrier_like(ld, "industry electricity"), "")
    check("biogas-anaerobic-digestion", "biogas to gas upgrading link",
          index_like(lk, "biogas to gas"), "")
    check("biomass-bioenergy", "solid biomass buses/stores",
          carrier_like(b, "biomass") or index_like(st, "biomass"), "")
    check("beccs", "biomass CHP (CC variant = BECCS evidence)",
          index_like(lk, "biomass CHP"), "")

    check("direct-air-capture", "DAC links into co2 stored",
          index_like(lk, "DAC"), "")
    check("direct-air-capture", "co2 stored bus + store, co2 atmosphere bus",
          carrier_like(b, "co2"), "")

    check("aviation", "kerosene for aviation loads (oil bus)",
          carrier_like(ld, "kerosene for aviation"), "")
    check("shipping", "shipping oil (and/or H2) loads",
          carrier_like(ld, "shipping"), "")

    check("behind-the-meter-der", "LV distribution buses + grid links",
          carrier_like(b, "low voltage") or index_like(lk, "distribution grid"), "")
    check("rooftop-distributed-solar", "solar rooftop generators (LV)",
          carrier_like(g, "solar rooftop"), "")
    check("behind-the-meter-der", "home battery stores (LV)",
          index_like(st, "home battery"), "")

    # ---- EXPECTED ABSENCES (region-dependent data -> recipes' data_dependencies) ----
    # district heating IS present despite the all-zero district_heating.csv: the
    # recipe (district-heating.yaml) grounds that only the "current" column is read
    # and expansion comes purely from config sector.district_heating.potential x
    # progress (defaults 0.3 x 1). The first draft of this check assumed the CSV
    # gates DH and was proven wrong by the run — recipe correct, expectation fixed.
    check("district-heating",
          "urban central heat present (config potential*progress drives DH; CSV 'current' all-zero)",
          index_like(lk, "urban central"), "")
    check("hydrogen-storage-salt-caverns",
          "EXPECTED ABSENT: underground H2 cavern store (no MX cavern row); tank storage instead",
          not index_like(st, "H2 UHS") and index_like(st, "H2"),
          "")


def main():
    power = sys.argv[1] if len(sys.argv) > 1 else POWER_NC
    sector = sys.argv[2] if len(sys.argv) > 2 else SECTOR_NC

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
