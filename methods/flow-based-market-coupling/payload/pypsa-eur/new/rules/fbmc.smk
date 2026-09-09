# SPDX-License-Identifier: MIT
#
# Flow-based market coupling — zygon methods payload
# `flow-based-market-coupling`. One dispatch-only rule on the clustered
# electricity pre-network: NTC + autarky auxiliary runs, hourly GSKs,
# flow-based parameters, FBMC clearing, nodal LMP benchmark. Window,
# zone map and all FB parameters come from the `fbmc:` config section.


rule solve_fbmc_market:
    input:
        network=resources("networks/base_s_{clusters}_elec_{opts}.nc"),
    output:
        network=RESULTS + "fbmc/base_s_{clusters}_elec_{opts}_fbmc.nc",
        fb_params=RESULTS + "fbmc/base_s_{clusters}_elec_{opts}_fbparams.nc",
        summary=RESULTS + "fbmc/base_s_{clusters}_elec_{opts}_fbmc_summary.csv",
    log:
        RESULTS + "logs/solve_fbmc_market/base_s_{clusters}_elec_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    params:
        fbmc=config_provider("fbmc"),
        solving=config_provider("solving"),
    message:
        "Clearing zonal market with flow-based coupling for {wildcards.clusters} clusters"
    script:
        scripts("solve_fbmc_market.py")
