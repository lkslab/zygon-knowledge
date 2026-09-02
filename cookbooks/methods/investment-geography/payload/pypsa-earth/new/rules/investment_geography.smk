# SPDX-License-Identifier: MIT
#
# Investment geography — zygon methods payload `investment-geography`
# (pypsa-earth tree). Distributes fixed per-country/technology capacity
# targets to buses as eta * cost-optimal + (1 - eta) * even-over-
# available-land (Thomassen et al. 2025 §3.2).


rule distribute_investment:
    params:
        invgeo=config["investment_geography"],
        solving=config["solving"],
    input:
        network="results/"
        + RDIR
        + "networks/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    output:
        network="results/"
        + RDIR
        + "invgeo/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_invgeo.nc",
        summary="results/"
        + RDIR
        + "invgeo/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_invgeo_summary.csv",
    log:
        "results/"
        + RDIR
        + "logs/distribute_investment_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/distribute_investment.py"
