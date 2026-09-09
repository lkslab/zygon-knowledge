# SPDX-License-Identifier: MIT
#
# Harmonised collection stage — zygon methods payload `multi-scenario`.
# ONE rule applied to every network of a problem: imports the agent-authored
# hooks module (zygon_collect.hooks, one function per quantity), applies
# every hook to every listed network, concatenates into one long-format CSV
# per quantity under results/zygon_collect/. Inputs are an EXPLICIT config
# list (zygon_collect.networks) so ANY solvable network set can be
# collected — this method's scenario variants, another method's horizon
# networks — the DAG schedules whatever is listed.


rule zygon_collect:
    params:
        labels=config["zygon_collect"]["labels"],
        quantities=config["zygon_collect"]["quantities"],
    input:
        networks=config["zygon_collect"]["networks"],
        hooks=config["zygon_collect"].get("hooks", "zygon_hooks.py"),
    output:
        csvs=expand(
            "results/zygon_collect/{quantity}.csv",
            quantity=config["zygon_collect"]["quantities"],
        ),
        manifest="results/zygon_collect/collect_manifest.json",
    log:
        "logs/zygon_collect.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/zygon_collect.py"
