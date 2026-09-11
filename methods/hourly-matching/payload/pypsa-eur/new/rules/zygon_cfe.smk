# SPDX-License-Identifier: MIT
#
# 24/7 clean procurement (Riepin et al. 2024) — zygon methods payload
# `hourly-matching`, shared with `annual-matching` (pypsa-eur tree). Each
# variant (config: zygon_cfe.variants.<label> = {window, score}) is the
# SETTLED composed network of one planning horizon plus ONE participating
# consumer and its procurement palette (build_cfe_network); solve_cfe_network
# mirrors the model's own solve_network rule (rules/solve.smk) and runs
# scripts/solve_network.py unchanged, but passes
# scripts/zygon_cfe_constraints.py as the rule's own custom_extra_functionality
# so the matching rule lands at solve time (the installed baseline sets
# solving.options.custom_extra_functionality to "", and any user hook is
# bypassed on THIS rule only). zygon_cfe_collect turns the run set into the
# study's numbers: procurement cost and premium per MWh, system-cost delta,
# ex-post CFE score, procured capacity, scope-2 emissions, grid exchange —
# plus the grid CFE factor series a second pass with import crediting reads.
#
# a6c45e5 streamlined workflow: networks are composed_{horizon}.nc /
# solved_{horizon}.nc, no cluster/opts wildcards; solve_network.py reads
# wildcards.horizon, so the {horizon} wildcard is kept on every path.
# Rebased 2026-09-10; not yet exercised against an a6c45e5 install.

import os


wildcard_constraints:
    zcfe="[a-z0-9][a-z0-9_-]*",


rule build_cfe_network:
    params:
        variant=lambda w: config["zygon_cfe"]["variants"][w.zcfe],
        cfe=config["zygon_cfe"],
    input:
        network=resources("networks/composed_{horizon}.nc"),
    output:
        resources("cfe/{zcfe}/composed_{horizon}.nc"),
    log:
        RESULTS + "logs/zygon_cfe/build_{zcfe}_composed_{horizon}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/build_cfe_network.py"


rule solve_cfe_network:
    input:
        network=resources("cfe/{zcfe}/composed_{horizon}.nc"),
    output:
        network=RESULTS + "cfe/{zcfe}/solved_{horizon}.nc",
        model=(
            RESULTS + "cfe/{zcfe}/models/solved_{horizon}.nc"
            if config["solving"]["options"]["store_model"]
            else []
        ),
    log:
        solver=normpath(RESULTS + "logs/zygon_cfe/{zcfe}_solver_{horizon}.log"),
        memory=RESULTS + "logs/zygon_cfe/{zcfe}_memory_{horizon}.log",
        python=RESULTS + "logs/zygon_cfe/{zcfe}_python_{horizon}.log",
    benchmark:
        (RESULTS + "benchmarks/solve_cfe_network/{zcfe}_{horizon}.log")
    shadow:
        shadow_config
    threads: solver_threads
    resources:
        mem_mb=config_provider("solving", "mem_mb"),
        runtime=config_provider("solving", "runtime", default="6h"),
    params:
        solving=config_provider("solving"),
        foresight=config_provider("foresight"),
        planning_horizons=config_provider("planning_horizons"),
        sector=config_provider("sector"),
        co2_sequestration_potential=config_provider(
            "sector", "co2_sequestration_potential"
        ),
        # the payload's own hook: solve_network.py imports this module and
        # calls the function named like the file (zygon_cfe_constraints)
        custom_extra_functionality=lambda w: os.path.join(
            workflow.basedir, "scripts", "zygon_cfe_constraints.py"
        ),
    message:
        "Solving clean-procurement variant {wildcards.zcfe} for horizon {wildcards.horizon}"
    script:
        scripts("solve_network.py")


rule zygon_cfe_collect:
    params:
        labels=config["zygon_cfe"]["labels"],
        reference=config["zygon_cfe"]["reference"],
        indicators=config["zygon_cfe"]["indicators"],
        cfe=config["zygon_cfe"],
    input:
        networks=config["zygon_cfe"]["networks"],
        baseline=config["zygon_cfe"].get("baseline", []),
    output:
        csvs=expand(
            "results/zygon_cfe/{indicator}.csv",
            indicator=config["zygon_cfe"]["indicators"],
        ),
        grid_cfe="results/zygon_cfe/grid_cfe_factor.csv",
        manifest="results/zygon_cfe/cfe_manifest.json",
    log:
        "logs/zygon_cfe_collect.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/zygon_cfe_collect.py"
