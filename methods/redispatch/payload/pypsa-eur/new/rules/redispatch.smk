# SPDX-License-Identifier: MIT
#
# Redispatch stage — zygon methods payload `redispatch`. Repairs a zonal
# market schedule into nodal feasibility with paid deviations
# (cost + volume objective, cross-zonal cap). Stage 1 is either cleared
# in-script (redispatch.stage1: ntc — standalone) or read from the
# flow-based-market-coupling payload's artifact (stage1: fbmc — requires
# that payload in the same bundle).


def _redispatch_stage1_input(w):
    if config_provider("redispatch", "stage1", default="ntc")(w) == "fbmc":
        return (RESULTS
                + f"fbmc/base_s_{w.clusters}_elec_{w.opts}_fbmc.nc")
    return []


rule solve_redispatch:
    input:
        network=resources("networks/base_s_{clusters}_elec_{opts}.nc"),
        stage1=_redispatch_stage1_input,
    output:
        network=RESULTS + "redispatch/base_s_{clusters}_elec_{opts}_rd.nc",
        summary=RESULTS + "redispatch/base_s_{clusters}_elec_{opts}_rd_summary.csv",
    log:
        RESULTS + "logs/solve_redispatch/base_s_{clusters}_elec_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    params:
        redispatch=config_provider("redispatch"),
        solving=config_provider("solving"),
    message:
        "Redispatching the zonal market schedule for {wildcards.clusters} clusters"
    script:
        scripts("solve_redispatch.py")
