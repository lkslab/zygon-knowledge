# SPDX-License-Identifier: MIT
#
# Redispatch stage — zygon methods payload `redispatch`. Repairs a zonal
# market schedule into nodal feasibility with paid deviations
# (cost + volume objective, cross-zonal cap). Stage 1 is either cleared
# in-script (redispatch.stage1: ntc — standalone) or read from the
# flow-based-market-coupling payload's artifact (stage1: fbmc — requires
# that payload in the same bundle).
#
# Reads the composed network of one planning horizon (a6c45e5 streamlined
# workflow, no wildcards). Rebased from base_s_{clusters}_elec_{opts}.nc on
# 2026-09-10; not yet exercised against an a6c45e5 install.


def _redispatch_stage1_input(w):
    if config_provider("redispatch", "stage1", default="ntc")(w) == "fbmc":
        return RESULTS + f"fbmc/composed_{w.horizon}_fbmc.nc"
    return []


rule solve_redispatch:
    input:
        network=resources("networks/composed_{horizon}.nc"),
        stage1=_redispatch_stage1_input,
    output:
        network=RESULTS + "redispatch/composed_{horizon}_rd.nc",
        summary=RESULTS + "redispatch/composed_{horizon}_rd_summary.csv",
    log:
        RESULTS + "logs/solve_redispatch/composed_{horizon}.log",
    threads: 1
    resources:
        mem_mb=4000,
    params:
        redispatch=config_provider("redispatch"),
        solving=config_provider("solving"),
    message:
        "Redispatching the zonal market schedule for horizon {wildcards.horizon}"
    script:
        scripts("solve_redispatch.py")
