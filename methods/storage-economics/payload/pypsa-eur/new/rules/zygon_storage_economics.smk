# SPDX-License-Identifier: MIT
#
# Storage economics — zygon methods payload `storage-economics`. ONE
# post-processing rule over an explicit list of solved networks (config:
# zygon_storage_economics.networks / labels — any solvable set composes:
# the baseline, a price-formation run, single-asset-cba variants, myopic
# horizons). Writes one long-format CSV per quantity under
# results/zygon_storage_economics/ with columns network, asset, carrier,
# bus, value.


rule zygon_storage_economics:
    params:
        labels=config["zygon_storage_economics"]["labels"],
        carriers=config["zygon_storage_economics"]["carriers"],
        quantities=config["zygon_storage_economics"]["quantities"],
    input:
        networks=config["zygon_storage_economics"]["networks"],
    output:
        csvs=expand(
            "results/zygon_storage_economics/{quantity}.csv",
            quantity=config["zygon_storage_economics"]["quantities"],
        ),
        manifest="results/zygon_storage_economics/storage_manifest.json",
    log:
        "logs/zygon_storage_economics.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/zygon_storage_economics.py"
