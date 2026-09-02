# baseline-pypsa-earth — Mexico reference (+ Costa Rica, Nigeria)

`config.yaml` here is the adopted cookbook-validation config (Mexico, 4
clusters, one week of 2013; power solve + sector prenetwork).
`config.cr.yaml` (Costa Rica) and `config.ng.yaml` (Nigeria) are the same
recipe verbatim with only run names, `countries:`, and (for NG) the cutout
swapped to `cutout-2013-era5-africa`; their baselines were built 2026-07-30
at the same submodule SHA and installed into the template alongside Mexico —
all three settle simultaneously (dry run proposes zero jobs per config). Unlike eur,
earth does NOT install a root config.yaml — its Snakefile loads
`config.default.yaml` and the baseline is applied per invocation:

    cd models/pypsa-earth
    <earth-env>/bin/snakemake -n <targets> --configfile <this dir>/config.yaml

GOTCHA: snakemake's `--configfile` and `--rerun-triggers` are nargs="+" —
targets listed AFTER them get swallowed as flag values (a .nc "configfile"
dies on the HDF5 magic byte). Always put targets before the flags.

Env: earth needs its OWN snakemake (7.x, `~/Desktop/earth/pypsa-earth/.pixi/
envs/default/bin`), not the eur env. Targets (from the config header):
  results/mexico-power/networks/elec_s_4_ec_lcopt_Co2L.nc            (solved)
  results/mexico-sector/prenetworks/elec_s_4_ec_lcopt_Co2L_144h_2030_0.071_AB.nc

Template state: retrieval payloads AND the per-country resources/results were
copied from the earth checkout, which is clean at exactly the submodule
commit (8435f4c8) — i.e. built by unmodified template code. Settle check
passed for all three configs; template is chmod -R a-w.

CO2 PIN (2026-07-30): all three configs set `automatic_emission: false` with
`co2limit`/`co2base` pinned to the EDGAR-derived values the runtime path
would have computed (MX 63963.909, CR 70.09494, NG 5698.76187 kt; 1990
power+heat, EDGAR v6.0 xls on disk in the earth checkout). Same numbers,
zero runtime downloads — `automatic_emission: true` re-downloads the EDGAR
inventory inside prepare_network and crashes offline (issue #1,
runs/issues/interview-evals-20260728.md). Baselines rebuilt + resettled with
these values; the template's mtime-settle discipline is documented in
runs/issues/README.md ("touch-settle").

MULTI-COUNTRY GOTCHA: `build_base_energy_totals` declares the SHARED cache
dir `data/demand/unsd/data` as an output while carrying per-run params
(`countries`, ...). Its metadata record therefore stores whichever run built
last, and every OTHER country's dry run fires a params trigger that cascades
through the whole sector chain (and, because the template omits the
`networks/<run>/` intermediates, re-derives the power chain too). Resolution:
that one record is DELETED from the template's `.snakemake/metadata/` (name:
`base64("data/demand/unsd/data")`). No provenance is lost — the rule's params
stay guarded by its run-scoped output record
(`resources/<run>-sector/energy_totals_base.csv`). If a future rebuild
re-creates the shared record, delete it again before the settle check.
Tracked as an issue (fix_layer: template) in `runs/issues/`.

The template intentionally carries NO `networks/<run>/` intermediates: a
settled run never needs them, and any bundle that invalidates the power
chain rebuilds them inside the runspace from scratch.
