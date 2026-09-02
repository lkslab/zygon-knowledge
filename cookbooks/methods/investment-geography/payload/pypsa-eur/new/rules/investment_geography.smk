# SPDX-License-Identifier: MIT
#
# Investment geography — zygon methods payload `investment-geography`.
# Distributes fixed per-country/technology capacity targets to buses as
# eta * cost-optimal + (1 - eta) * even-over-available-land
# (Thomassen et al. 2025 §3.2 auction-effectiveness mechanism).


rule distribute_investment:
    input:
        network=resources("networks/base_s_{clusters}_elec_{opts}.nc"),
    output:
        network=RESULTS + "invgeo/base_s_{clusters}_elec_{opts}_invgeo.nc",
        summary=RESULTS + "invgeo/base_s_{clusters}_elec_{opts}_invgeo_summary.csv",
    log:
        RESULTS + "logs/distribute_investment/base_s_{clusters}_elec_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    params:
        invgeo=config_provider("investment_geography"),
        solving=config_provider("solving"),
    message:
        "Distributing auction-target capacity for {wildcards.clusters} clusters"
    script:
        scripts("distribute_investment.py")
