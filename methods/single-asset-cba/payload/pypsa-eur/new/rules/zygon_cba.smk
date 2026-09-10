# SPDX-License-Identifier: MIT
#
# Single-asset CBA (TOOT/PINT) — zygon methods payload `single-asset-cba`
# (pypsa-eur tree). ENTSO-E CBA-guideline project assessment: each variant is
# the SETTLED composed network of one planning horizon with an ordered
# operation list applied (config: zygon_cba.variants — the reference label
# carries an empty list and is re-solved untouched; pint-*/toot-* labels put
# one asset in / take one out, an asset possibly spanning several
# components). solve_cba_network mirrors the model's own solve_network rule
# (rules/solve.smk) and runs scripts/solve_network.py unchanged;
# zygon_cba_collect computes the guideline's direction-signed benefit
# indicators (B1 SEW / B2 CO2 / B3 RES) per perturbed variant against the
# reference.
#
# a6c45e5 streamlined workflow: networks are composed_{horizon}.nc /
# solved_{horizon}.nc, no cluster/opts wildcards; solve_network.py reads
# wildcards.horizon, so the {horizon} wildcard is kept on every path.
# Rebased 2026-09-10; not yet exercised against an a6c45e5 install.


wildcard_constraints:
    zcba="[a-z0-9][a-z0-9_-]*",


rule build_cba_network:
    params:
        variant=lambda w: config["zygon_cba"]["variants"][w.zcba],
        reference=config["zygon_cba"]["reference"],
    input:
        network=resources("networks/composed_{horizon}.nc"),
    output:
        resources("cba/{zcba}/composed_{horizon}.nc"),
    log:
        RESULTS + "logs/zygon_cba/build_{zcba}_composed_{horizon}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/build_cba_network.py"


rule solve_cba_network:
    input:
        network=resources("cba/{zcba}/composed_{horizon}.nc"),
    output:
        network=RESULTS + "cba/{zcba}/solved_{horizon}.nc",
        model=(
            RESULTS + "cba/{zcba}/models/solved_{horizon}.nc"
            if config["solving"]["options"]["store_model"]
            else []
        ),
    log:
        solver=normpath(RESULTS + "logs/zygon_cba/{zcba}_solver_{horizon}.log"),
        memory=RESULTS + "logs/zygon_cba/{zcba}_memory_{horizon}.log",
        python=RESULTS + "logs/zygon_cba/{zcba}_python_{horizon}.log",
    benchmark:
        (RESULTS + "benchmarks/solve_cba_network/{zcba}_{horizon}.log")
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
        custom_extra_functionality=input_custom_extra_functionality,
    message:
        "Solving CBA variant {wildcards.zcba} for horizon {wildcards.horizon}"
    script:
        scripts("solve_network.py")


rule zygon_cba_collect:
    params:
        labels=config["zygon_cba"]["labels"],
        reference=config["zygon_cba"]["reference"],
        indicators=config["zygon_cba"]["indicators"],
    input:
        networks=config["zygon_cba"]["networks"],
    output:
        csvs=expand(
            "results/zygon_cba/{indicator}.csv",
            indicator=config["zygon_cba"]["indicators"],
        ),
        manifest="results/zygon_cba/cba_manifest.json",
    log:
        "logs/zygon_cba_collect.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/zygon_cba_collect.py"
