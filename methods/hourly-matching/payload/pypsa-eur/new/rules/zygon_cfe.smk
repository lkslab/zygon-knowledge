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
# Streamlined workflow (a6c45e5 and later): networks are composed_{horizon}.nc
# / solved_{horizon}.nc, no cluster/opts wildcards; solve_network.py reads
# wildcards.horizon, so the {horizon} wildcard is kept on every path. Every
# zygon_cfe.* value is read through config_provider, so under run.scenarios a
# scenario's own labels/variants apply to its {run}; the collect rule is
# per-run for the same reason (results/{run}/zygon_cfe/<indicator>.csv).
# Dry-run validated against 82b13507 (lkslab/pypsa-eur, 2026-09-16).

import os

# This rule file's own directory, captured at parse time (a lambda runs later,
# when the included-file stack no longer points here). The payload's scripts sit
# beside it in ../scripts, wherever the tree is staged.
_ZYGON_CFE_RULES_DIR = workflow.current_basedir.get_path_or_uri()


def _zygon_cfe_solar_capacity_per_sqkm(w):
    # solve_network.py at 82b13507 reads params.solar_capacity_per_sqkm when
    # solar and solar-hsat are both renewable and extendable; rules/solve.smk
    # defines the provider there. a6c45e5a has neither, hence the fallback.
    provider = globals().get("solar_capacity_per_sqkm_provider")
    return provider(w) if provider is not None else {}


def _zygon_cfe_run_expand(pattern, w, **kw):
    # RESULTS carries a {run} wildcard only under run.scenarios.
    if "{run}" in pattern:
        kw["run"] = [w.run]
    return expand(pattern, **kw)


def _zygon_cfe_solved(w):
    """The solved variant networks of one run: its own labels, last horizon."""
    labels = config_provider("zygon_cfe", "labels")(w)
    horizon = config_provider("planning_horizons")(w)[-1]
    return _zygon_cfe_run_expand(
        RESULTS + "cfe/{zcfe}/solved_{horizon}.nc", w, zcfe=labels, horizon=[horizon]
    )


def _zygon_cfe_baseline(w):
    """The run's own solved network (no consumer), when zygon_cfe.baseline is
    true, for the additionality reading."""
    if not config_provider("zygon_cfe", "baseline", default=False)(w):
        return []
    horizon = config_provider("planning_horizons")(w)[-1]
    return _zygon_cfe_run_expand(
        RESULTS + "networks/solved_{horizon}.nc", w, horizon=[horizon]
    )


wildcard_constraints:
    zcfe="[a-z0-9][a-z0-9_-]*",


rule build_cfe_network:
    params:
        variant=lambda w: config_provider("zygon_cfe", "variants")(w)[w.zcfe],
        cfe=config_provider("zygon_cfe"),
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
        solar_capacity_per_sqkm=_zygon_cfe_solar_capacity_per_sqkm,
        # the variant set of THIS run, read by zygon_cfe_constraints
        cfe=config_provider("zygon_cfe"),
        # the payload's own hook: solve_network.py imports this module and
        # calls the function named like the file (zygon_cfe_constraints)
        custom_extra_functionality=lambda w: os.path.join(
            _ZYGON_CFE_RULES_DIR, "..", "scripts", "zygon_cfe_constraints.py"
        ),
    message:
        "Solving clean-procurement variant {wildcards.zcfe} for horizon {wildcards.horizon}"
    script:
        scripts("solve_network.py")


rule zygon_cfe_collect:
    params:
        labels=config_provider("zygon_cfe", "labels"),
        reference=config_provider("zygon_cfe", "reference"),
        indicators=config_provider("zygon_cfe", "indicators"),
        cfe=config_provider("zygon_cfe"),
    input:
        networks=_zygon_cfe_solved,
        baseline=_zygon_cfe_baseline,
    output:
        csvs=expand(
            RESULTS + "zygon_cfe/{indicator}.csv",
            indicator=config["zygon_cfe"]["indicators"],
            allow_missing=True,
        ),
        grid_cfe=RESULTS + "zygon_cfe/grid_cfe_factor.csv",
        manifest=RESULTS + "zygon_cfe/cfe_manifest.json",
    log:
        RESULTS + "logs/zygon_cfe_collect.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/zygon_cfe_collect.py"
