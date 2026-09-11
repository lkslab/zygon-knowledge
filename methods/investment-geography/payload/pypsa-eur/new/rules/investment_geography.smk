# SPDX-License-Identifier: MIT
#
# Investment geography — zygon methods payload `investment-geography`.
# Distributes fixed per-country/technology capacity targets to buses as
# eta * cost-optimal + (1 - eta) * even-over-available-land
# (Thomassen et al. 2025 §3.2 auction-effectiveness mechanism).
#
# Reads the composed network of one planning horizon (a6c45e5 streamlined
# workflow, no wildcards). Rebased from base_s_{clusters}_elec_{opts}.nc on
# 2026-09-10; not yet exercised against an a6c45e5 install.


rule distribute_investment:
    input:
        network=resources("networks/composed_{horizon}.nc"),
    output:
        network=RESULTS + "invgeo/composed_{horizon}_invgeo.nc",
        summary=RESULTS + "invgeo/composed_{horizon}_invgeo_summary.csv",
    log:
        RESULTS + "logs/distribute_investment/composed_{horizon}.log",
    threads: 1
    resources:
        mem_mb=4000,
    params:
        invgeo=config_provider("investment_geography"),
        solving=config_provider("solving"),
    message:
        "Distributing auction-target capacity for horizon {wildcards.horizon}"
    script:
        scripts("distribute_investment.py")
