# SPDX-License-Identifier: MIT
#
# Redispatch stage — zygon methods payload `redispatch` (pypsa-earth
# tree). Repairs a zonal market schedule into nodal feasibility with paid
# deviations (cost + volume objective, cross-zonal cap). Stage 1 is
# either cleared in-script (redispatch.stage1: ntc — standalone) or read
# from the flow-based-market-coupling payload's artifact (stage1: fbmc —
# requires that payload in the same bundle).


def _redispatch_stage1_input(w):
    if config["redispatch"].get("stage1", "ntc") == "fbmc":
        return ("results/" + RDIR
                + f"fbmc/elec_s{w.simpl}_{w.clusters}_ec_l{w.ll}_{w.opts}_fbmc.nc")
    return []


rule solve_redispatch:
    params:
        redispatch=config["redispatch"],
        solving=config["solving"],
    input:
        network="results/"
        + RDIR
        + "networks/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
        stage1=_redispatch_stage1_input,
    output:
        network="results/"
        + RDIR
        + "redispatch/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_rd.nc",
        summary="results/"
        + RDIR
        + "redispatch/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_rd_summary.csv",
    log:
        "results/"
        + RDIR
        + "logs/solve_redispatch_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/solve_redispatch.py"
