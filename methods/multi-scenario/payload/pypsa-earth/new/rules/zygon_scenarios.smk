# SPDX-License-Identifier: MIT
#
# Declarative scenario fan-out — zygon methods payload `multi-scenario`
# (pypsa-earth tree; pypsa-eur uses the model's native run.scenarios
# mechanism instead). Earth has no per-run config override machinery, so
# variants are expressed as ordered operation lists applied to the SETTLED
# prepared electricity network (config: zygon_scenarios.variants — see
# config.default.yaml). Boundary: parameters visible on the prepared
# network object only; upstream variants (clustering, weather year, demand)
# are out of scope on earth.
#
# solve_scenario_network reuses the model's OWN scripts/solve_network.py —
# variants are solved exactly like the baseline.


wildcard_constraints:
    zscen="[a-z0-9][a-z0-9_-]*",


rule build_scenario_network:
    params:
        variant=lambda w: config["zygon_scenarios"]["variants"][w.zscen],
    input:
        network="networks/" + RDIR + "elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    output:
        "networks/"
        + RDIR
        + "scenarios/{zscen}/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    log:
        "logs/"
        + RDIR
        + "build_scenario_network/{zscen}_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/build_scenario_network.py"


rule solve_scenario_network:
    params:
        solving=config["solving"],
        augmented_line_connection=config["augmented_line_connection"],
        policy_config=config["policy_config"],
    input:
        network="networks/"
        + RDIR
        + "scenarios/{zscen}/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
        agg_p_nom_minmax=config["electricity"]["agg_p_nom_limits"]["file"],  # ensure the CSV with capacity constraints is copied into the shadow directory (needed on Windows, since shadowed scripts can’t access files outside `input`)
    output:
        "results/"
        + RDIR
        + "scenarios/{zscen}/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    log:
        solver=os.path.normpath(
            "logs/"
            + RDIR
            + "solve_scenario_network/{zscen}_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_solver.log"
        ),
        python="logs/"
        + RDIR
        + "solve_scenario_network/{zscen}_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_python.log",
    threads: 4
    resources:
        mem_mb=8000,
    shadow:
        "copy-minimal" if os.name == "nt" else "shallow"
    script:
        "../scripts/solve_network.py"
