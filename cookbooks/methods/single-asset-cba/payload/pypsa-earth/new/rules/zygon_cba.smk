# SPDX-License-Identifier: MIT
#
# Single-asset CBA (TOOT/PINT) — zygon methods payload `single-asset-cba`
# (pypsa-earth tree). ENTSO-E CBA-guideline project assessment: each variant
# is the SETTLED prepared electricity network with an ordered operation list
# applied (config: zygon_cba.variants — the reference label carries an empty
# list and is re-solved untouched; pint-*/toot-* labels put one asset in /
# take one out, an asset possibly spanning several components).
# solve_cba_network reuses the model's OWN scripts/solve_network.py —
# variants are solved exactly like the baseline; zygon_cba_collect computes
# the guideline's direction-signed benefit indicators (B1 SEW / B2 CO2 /
# B3 RES) per perturbed variant against the reference.


wildcard_constraints:
    zcba="[a-z0-9][a-z0-9_-]*",


rule build_cba_network:
    params:
        variant=lambda w: config["zygon_cba"]["variants"][w.zcba],
        reference=config["zygon_cba"]["reference"],
    input:
        network="networks/" + RDIR + "elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    output:
        "networks/"
        + RDIR
        + "cba/{zcba}/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    log:
        "logs/"
        + RDIR
        + "build_cba_network/{zcba}_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.log",
    threads: 1
    resources:
        mem_mb=4000,
    script:
        "../scripts/build_cba_network.py"


rule solve_cba_network:
    params:
        solving=config["solving"],
        augmented_line_connection=config["augmented_line_connection"],
        policy_config=config["policy_config"],
    input:
        network="networks/"
        + RDIR
        + "cba/{zcba}/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
        agg_p_nom_minmax=config["electricity"]["agg_p_nom_limits"]["file"],  # ensure the CSV with capacity constraints is copied into the shadow directory (needed on Windows, since shadowed scripts can’t access files outside `input`)
    output:
        "results/"
        + RDIR
        + "cba/{zcba}/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
    log:
        solver=os.path.normpath(
            "logs/"
            + RDIR
            + "solve_cba_network/{zcba}_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_solver.log"
        ),
        python="logs/"
        + RDIR
        + "solve_cba_network/{zcba}_elec_s{simpl}_{clusters}_ec_l{ll}_{opts}_python.log",
    threads: 4
    resources:
        mem_mb=8000,
    shadow:
        "copy-minimal" if os.name == "nt" else "shallow"
    script:
        "../scripts/solve_network.py"


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
