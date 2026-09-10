# SPDX-License-Identifier: MIT
#
# Flow-based market coupling — zygon methods payload
# `flow-based-market-coupling` (pypsa-earth tree). One dispatch-only rule
# on the solved electricity network: NTC + autarky auxiliary runs, hourly
# GSKs, flow-based parameters, FBMC clearing, nodal LMP benchmark.
# Window, zone map and all FB parameters come from the `fbmc:` config
# section.


rule solve_fbmc_market:
    params:
        fbmc=config["fbmc"],
        solving=config["solving"],
    input:
        network="results/"
        + RDIR
        + "networks/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    output:
        network="results/"
        + RDIR
        + "fbmc/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_fbmc.nc",
        fb_params="results/"
        + RDIR
        + "fbmc/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_fbparams.nc",
        summary="results/"
        + RDIR
        + "fbmc/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_fbmc_summary.csv",
    log:
        "results/"
        + RDIR
        + "logs/solve_fbmc_market_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/solve_fbmc_market.py"
