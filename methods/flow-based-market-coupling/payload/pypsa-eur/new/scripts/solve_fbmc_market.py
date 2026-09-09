# Zonal market clearing under flow-based market coupling — snakemake entry.
#
# Shipped by the zygon methods payload `flow-based-market-coupling`.
# Consumes the clustered electricity pre-network (hourly profiles, existing
# fleet) and runs the Thomassen et al. (2025) short-term operations chain on
# a config-selected snapshot window:
#
#   nodal PTDFs -> NTC auxiliary run -> autarky run -> hourly GSKs
#     -> flow-based parameters (zPTDF, F0, RAM) -> FBMC clearing
#     -> nodal LMP benchmark for comparison
#
# Outputs
#   network:   the sliced pypsa network carrying the FBMC market dispatch
#              (generators_t.p incl. 'load shedding' generators), zonal
#              prices broadcast to buses_t.marginal_price, and a
#              self-describing summary under n.meta['fbmc'] — the artifact
#              success metrics and downstream redispatch consume.
#   fb_params: netCDF with GSK, zPTDF, F0, RAM tensors (diagnostics).
#   summary:   one-row csv of the headline comparison numbers.

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa
import xarray as xr

sys.path.insert(0, str(Path(__file__).parent))
from fbmc_core import (  # noqa: E402
    compute_fb_params, compute_gsk, compute_ptdf, dispatch_cost,
    extract_market_data, make_ntcs, overloads, select_cnecs, solve_nodal,
    solve_zonal,
)

logger = logging.getLogger(__name__)


def run(n, cfg, solver_name, solver_options):
    d = extract_market_data(n, cfg)
    ptdf = compute_ptdf(d["nodes"], d["lines"])
    hybrid = cfg.get("hybrid_coupling", "advanced")
    ntcs = make_ntcs(d, float(cfg.get("ntc_haircut", 0.7)), hybrid)
    if hybrid == "standard":
        d = dict(d, dc=d["dc"].iloc[0:0])  # DC folded into the NTCs

    solve = dict(solver_name=solver_name, solver_options=solver_options)
    res = {}
    res["nodal"] = solve_nodal(d, **solve)
    res["ntc"] = solve_zonal(d, "ntc", ntc=ntcs, **solve)
    res["autarky"] = solve_zonal(d, "ntc", ntc=ntcs * 0.0, **solve)

    gcfg = cfg.get("gsk") or {}
    gsk, fallback = compute_gsk(d, res["ntc"], res["autarky"],
                                variant=gcfg.get("variant", "optimized"),
                                eps_mw=float(gcfg.get("eps_mw", 50.0)))
    ccfg = cfg.get("cnec") or {}
    cnecs = select_cnecs(d, ptdf, float(ccfg.get("threshold", 0.05)),
                         bool(ccfg.get("ties_always", True)))
    fb = compute_fb_params(d, ptdf, gsk, res["autarky"],
                           float(cfg.get("frm", 0.1)),
                           float(cfg.get("minram", 0.1)), cnecs)
    res["fbmc"] = solve_zonal(d, "fbmc", fb=fb, **solve)
    return d, ptdf, gsk, fallback, fb, res


def summarize(d, ptdf, fallback, fb, res):
    shed_idx = d["gens"].index[d["gens"].carrier == "load shedding"]
    rows = {}
    for design in ("nodal", "ntc", "fbmc"):
        r = res[design]
        _, ov = overloads(d, ptdf, r["g"], r["fdc"].values)
        price = r["lmp"] if design == "nodal" else r["price"]
        rows[design] = dict(
            market_cost=dispatch_cost(d, r["g"]),
            overload_mwh=float(ov.values.sum()),
            shed_mwh=float(r["g"].loc[shed_idx].values.sum()),
            price_std=float(price.std(axis=0).mean()),
            price_mean=float(price.values.mean()),
        )
    fbmc = res["fbmc"]
    tol = 1e-4
    binding = int(((fb["ram_pos"].loc[fb["cnecs"]]
                    - _fcnec(d, fb, fbmc)).abs() < tol).values.sum()
                  + ((_fcnec(d, fb, fbmc)
                      - fb["ram_neg"].loc[fb["cnecs"]]).abs() < tol)
                  .values.sum())
    r3 = lambda s: [round(float(v), 3) for v in s]  # noqa: E731
    hourly = dict(
        zone_price={z: r3(res["fbmc"]["price"].loc[z])
                    for z in res["fbmc"]["price"].index},
        ntc_zone_price={z: r3(res["ntc"]["price"].loc[z])
                        for z in res["ntc"]["price"].index},
        nodal_min=r3(res["nodal"]["lmp"].min(axis=0)),
        nodal_mean=r3(res["nodal"]["lmp"].mean(axis=0)),
        nodal_max=r3(res["nodal"]["lmp"].max(axis=0)),
    )
    return dict(
        designs=rows,
        hourly=hourly,
        nodal_cost=rows["nodal"]["market_cost"],
        ntc_cost=rows["ntc"]["market_cost"],
        market_cost=rows["fbmc"]["market_cost"],
        nodal_price_std=rows["nodal"]["price_std"],
        zonal_price_std=rows["fbmc"]["price_std"],
        overload_mwh=rows["fbmc"]["overload_mwh"],
        binding_cnecs=binding,
        np_closure_max=float(res["fbmc"]["npos"].sum(axis=0).abs().max()),
        gsk_fallback_share={z: float(v) for z, v in fallback.items()},
        n_cnecs=int(len(fb["cnecs"])),
        n_zones=len(d["zones"]),
        n_hours=len(d["t"]),
        window=[str(d["snapshots"][0]), str(d["snapshots"][-1])],
        zones={b: str(z) for b, z in d["nodes"].zone.items()},
        design="fbmc",
    )


def _fcnec(d, fb, run):
    """Realized CNEC flows of a zonal run under the FB linear map."""
    Z, T = len(d["zones"]), len(d["t"])
    zp = fb["zptdf"].loc[fb["cnecs"]].values.reshape(-1, Z, T)
    f = np.einsum("lzt,zt->lt", zp, run["npos"].values)
    if len(d["dc"]):
        f = f + fb["ptdf_dc"].loc[fb["cnecs"]].values @ run["fdc"].values
    return pd.DataFrame(f, index=fb["cnecs"], columns=d["t"])


def export_network(n, d, res, meta, path):
    """The sliced network with the FBMC market dispatch written in — the
    interface artifact any redispatch stage (and the success metrics)
    consume."""
    out = n.copy(snapshots=d["snapshots"])
    fbmc = res["fbmc"]
    shed = d["gens"][d["gens"].carrier == "load shedding"]
    shed = shed[~shed.index.isin(out.generators.index)]
    if "load shedding" not in out.carriers.index:
        out.add("Carrier", "load shedding")
    # pypsa >=1.0 adds many components via add(); 0.x needs madd()
    add_many = out.madd if hasattr(out, "madd") else out.add
    add_many("Generator", shed.index, bus=shed.node.values,
             carrier="load shedding", p_nom=shed.cap.values,
             marginal_cost=shed.mc.values)

    disp = fbmc["g"].T.set_axis(d["snapshots"], axis=0)
    out.generators_t.p = disp.reindex(columns=out.generators.index,
                                      fill_value=0.0)
    if len(d["dc"]):
        dcp = fbmc["fdc"].T.set_axis(d["snapshots"], axis=0)
        out.links_t.p0 = dcp.reindex(columns=out.links.index,
                                     fill_value=0.0)
    zone_price = fbmc["price"].T.set_axis(d["snapshots"], axis=0)
    bus_price = pd.DataFrame(
        0.0, index=d["snapshots"], columns=out.buses.index)
    for b, z in d["nodes"].zone.items():
        bus_price[b] = zone_price[z]
    out.buses_t.marginal_price = bus_price
    out.meta = dict(out.meta, fbmc=meta)
    out.export_to_netcdf(path)


def export_fb_params(d, gsk, fb, path):
    Z, T = len(d["zones"]), len(d["t"])
    zptdf = fb["zptdf"].values.reshape(len(d["lines"]), Z, T)
    ds = xr.Dataset(
        dict(
            zptdf=(("line", "zone", "t"), zptdf),
            gsk=(("node", "t"), gsk.values),
            f0=(("line", "t"), fb["f0"].values),
            ram_pos=(("line", "t"), fb["ram_pos"].values),
            ram_neg=(("line", "t"), fb["ram_neg"].values),
        ),
        coords=dict(line=d["lines"].index, zone=d["zones"],
                    t=d["t"].values, node=d["nodes"].index,
                    cnec=("cnec", list(fb["cnecs"]))),
    )
    ds.to_netcdf(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    cfg = dict(snakemake.params.fbmc)  # noqa: F821
    solving = snakemake.params.solving  # noqa: F821
    solver_name = solving["solver"]["name"]
    solver_options = solving.get("solver_options", {}).get(
        solving["solver"].get("options", ""), {})

    n = pypsa.Network(snakemake.input.network)  # noqa: F821
    d, ptdf, gsk, fallback, fb, res = run(n, cfg, solver_name,
                                          solver_options)
    meta = summarize(d, ptdf, fallback, fb, res)

    logger.info("FBMC day run: nodal %.0f | ntc %.0f | fbmc %.0f EUR; "
                "%d/%d CNEC constraints binding; np closure %.2e MW",
                meta["nodal_cost"], meta["ntc_cost"], meta["market_cost"],
                meta["binding_cnecs"], meta["n_cnecs"],
                meta["np_closure_max"])

    export_network(n, d, res, meta, snakemake.output.network)  # noqa: F821
    export_fb_params(d, gsk, fb, snakemake.output.fb_params)  # noqa: F821
    flat = {k: v for k, v in meta.items()
            if isinstance(v, (int, float, str))}
    pd.DataFrame([flat]).to_csv(snakemake.output.summary,  # noqa: F821
                                index=False)
