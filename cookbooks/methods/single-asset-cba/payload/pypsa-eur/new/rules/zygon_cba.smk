# SPDX-License-Identifier: MIT
#
# Single-asset CBA (TOOT/PINT) — zygon methods payload `single-asset-cba`
# (pypsa-eur tree). ENTSO-E CBA-guideline project assessment: each variant is
# the SETTLED prepared sector network with an ordered operation list applied
# (config: zygon_cba.variants — the reference label carries an empty list and
# is re-solved untouched; pint-*/toot-* labels put one asset in / take one
# out, an asset possibly spanning several components). solve_cba_network
# mirrors the model's own solve_sector_network and runs
# scripts/solve_network.py unchanged; zygon_cba_collect computes the
# guideline's direction-signed benefit indicators (B1 SEW / B2 CO2 / B3 RES)
# per perturbed variant against the reference.


wildcard_constraints:
    zcba="[a-z0-9][a-z0-9_-]*",


rule build_cba_network:
    params:
        variant=lambda w: config["zygon_cba"]["variants"][w.zcba],
        reference=config["zygon_cba"]["reference"],
    input:
        network=resources(
            "networks/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
        ),
    output:
        resources(
            "cba/{zcba}/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
        ),
    log:
        RESULTS
        + "logs/zygon_cba/build_{zcba}_base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/build_cba_network.py"


rule solve_cba_network:
    input:
        network=resources(
            "cba/{zcba}/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
        ),
    output:
        network=RESULTS
        + "cba/{zcba}/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc",
        config=RESULTS
        + "cba/{zcba}/configs/config.base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.yaml",
        model=(
            RESULTS
            + "cba/{zcba}/models/base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}.nc"
            if config["solving"]["options"]["store_model"]
            else []
        ),
    log:
        solver=RESULTS
        + "logs/zygon_cba/{zcba}_base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}_solver.log",
        memory=RESULTS
        + "logs/zygon_cba/{zcba}_base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}_memory.log",
        python=RESULTS
        + "logs/zygon_cba/{zcba}_base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}_python.log",
    benchmark:
        (
            RESULTS
            + "benchmarks/solve_cba_network/{zcba}_base_s_{clusters}_{opts}_{sector_opts}_{planning_horizons}"
        )
    shadow:
        shadow_config
    threads: solver_threads
    resources:
        mem_mb=config_provider("solving", "mem_mb"),
        runtime=config_provider("solving", "runtime", default="6h"),
    params:
        solving=config_provider("solving"),
        foresight=config_provider("foresight"),
        co2_sequestration_potential=config_provider(
            "sector", "co2_sequestration_potential", default=200
        ),
        custom_extra_functionality=input_custom_extra_functionality,
    message:
        "Solving CBA variant {wildcards.zcba} of the prepared sector network"
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
