# SPDX-License-Identifier: MIT
#
# Flow-based market coupling — zygon methods payload
# `flow-based-market-coupling`. One dispatch-only rule on the composed
# network (a6c45e5 streamlined workflow: one file per planning horizon, no
# wildcards): NTC + autarky auxiliary runs, hourly GSKs, flow-based
# parameters, FBMC clearing, nodal LMP benchmark. Window, zone map and all
# FB parameters come from the `fbmc:` config section.
#
# Rebased from the wildcard-era rule (base_s_{clusters}_elec_{opts}.nc) on
# 2026-09-10; not yet exercised against an a6c45e5 install.


rule solve_fbmc_market:
    input:
        network=resources("networks/composed_{horizon}.nc"),
    output:
        network=RESULTS + "fbmc/composed_{horizon}_fbmc.nc",
        fb_params=RESULTS + "fbmc/composed_{horizon}_fbparams.nc",
        summary=RESULTS + "fbmc/composed_{horizon}_fbmc_summary.csv",
    log:
        RESULTS + "logs/solve_fbmc_market/composed_{horizon}.log",
    threads: 1
    resources:
        mem_mb=4000,
    params:
        fbmc=config_provider("fbmc"),
        solving=config_provider("solving"),
    message:
        "Clearing zonal market with flow-based coupling for horizon {wildcards.horizon}"
    script:
        "../scripts/solve_fbmc_market.py"
