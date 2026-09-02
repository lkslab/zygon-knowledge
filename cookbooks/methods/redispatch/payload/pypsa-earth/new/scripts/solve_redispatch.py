# Redispatch stage — snakemake entry.
#
# Shipped by the zygon methods payload `redispatch`. Consumes ANY stage-1
# market schedule and repairs it into feasibility on the full nodal
# network, booking the remedial volume and cost (Thomassen et al. 2025
# §3.4). Two stage-1 sources, selected by `redispatch.stage1`:
#
#   ntc  — self-contained: this script clears a zonal NTC market on the
#          electricity pre-network first (the standalone verification path)
#   fbmc — reads the flow-based-market-coupling payload's artifact
#          (results/.../fbmc/..._fbmc.nc) as the schedule; zone map and
#          window are taken from ITS meta so the two stages stay aligned
#
# Output network carries the POST-redispatch dispatch and a
# n.meta['redispatch'] summary block (volume, cost, pre/post overloads,
# up/down split by carrier class, cross-zonal share).

import logging
import sys
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).parent))
from redispatch_core import (  # noqa: E402
    THERMAL_CARRIERS, VRE_CARRIERS, compute_ptdf, dispatch_cost,
    extract_market_data, make_ntcs, overloads, solve_redispatch,
    solve_zonal_ntc,
)

logger = logging.getLogger(__name__)


def stage1_from_fbmc(d, stage1_net):
    """Map the FBMC artifact's market dispatch onto the extracted dataset.
    Generator and DC-link names are shared because both payloads extract
    identically from the same pre-network."""
    g = stage1_net.generators_t.p.T
    g.columns = range(len(g.columns))
    g_star = g.reindex(d["gens"].index).fillna(0.0)[d["t"]]
    if len(d["dc"]):
        fdc = stage1_net.links_t.p0.T.reindex(d["dc"].index).fillna(0.0)
        fdc.columns = range(len(fdc.columns))
        fdc = fdc[d["t"]]
    else:
        fdc = pd.DataFrame(0.0, index=d["dc"].index, columns=d["t"])
    market_cost = dispatch_cost(d, g_star)
    return g_star, fdc, market_cost


def resolve_beta(cfg, d):
    """Thomassen's rule: the volume penalty must exceed the maximum
    marginal-cost spread so VOLUME dominates and the stage never does
    economic re-optimization (un-shedding arbitrage, intra-zonal merit
    swaps). 'auto' = max spread + 1; a number is taken as-is."""
    beta = cfg.get("beta", "auto")
    if isinstance(beta, str):
        if beta != "auto":
            raise ValueError(f"redispatch.beta must be 'auto' or a number,"
                             f" got {beta!r}")
        return float(d["mc"].values.max() - d["mc"].values.min()) + 1.0
    return float(beta)


def summarize(d, ptdf, g_star, fdc_star, rd, stage1, market_cost, cfg):
    _, ov_pre = overloads(d, ptdf, g_star, fdc_star.values)
    _, ov_post = overloads(d, ptdf, rd["g"], fdc_star.values)
    carriers = d["gens"].carrier
    vre = carriers[carriers.isin(VRE_CARRIERS)].index
    thermal = carriers[carriers.isin(THERMAL_CARRIERS)].index
    up_by_zone = rd["rup"].sum(axis=1).groupby(d["gens"].zone).sum()
    down_by_zone = rd["rdn"].sum(axis=1).groupby(d["gens"].zone).sum()
    up_by_bus = rd["rup"].sum(axis=1).groupby(d["gens"].node).sum()
    down_by_bus = rd["rdn"].sum(axis=1).groupby(d["gens"].node).sum()
    return dict(
        stage1_design=stage1,
        market_cost=market_cost,
        rd_cost=rd["rd_cost"],
        total_cost=market_cost + rd["rd_cost"],
        volume_mwh=rd["volume"],
        volume_up_mwh=rd["volume_up"],
        volume_dn_mwh=rd["volume_dn"],
        overload_pre_mwh=float(ov_pre.values.sum()),
        overload_post_mwh=float(ov_post.values.sum()),
        vre_down_mwh=float(rd["rdn"].loc[vre].values.sum()),
        thermal_up_mwh=float(rd["rup"].loc[thermal].values.sum()),
        up_by_zone={z: float(v) for z, v in up_by_zone.items()},
        down_by_zone={z: float(v) for z, v in down_by_zone.items()},
        top_up_bus=str(up_by_bus.idxmax()),
        top_down_bus=str(down_by_bus.idxmax()),
        cross_zonal_share=rd["cross_zonal_share"],
        cross_zonal_cap=cfg.get("cross_zonal_cap"),
        congested_zones=rd["congested_zones"],
        beta=resolve_beta(cfg, d),
        n_zones=len(d["zones"]),
        n_hours=len(d["t"]),
        window=[str(d["snapshots"][0]), str(d["snapshots"][-1])],
        zones={b: str(z) for b, z in d["nodes"].zone.items()},
    )


def export_network(n, d, rd, meta, path):
    out = n.copy(snapshots=d["snapshots"])
    shed = d["gens"][d["gens"].carrier == "load shedding"]
    shed = shed[~shed.index.isin(out.generators.index)]
    if "load shedding" not in out.carriers.index:
        out.add("Carrier", "load shedding")
    # pypsa >=1.0 adds many components via add(); 0.x needs madd()
    add_many = out.madd if hasattr(out, "madd") else out.add
    add_many("Generator", shed.index, bus=shed.node.values,
             carrier="load shedding", p_nom=shed.cap.values,
             marginal_cost=shed.mc.values)
    disp = rd["g"].T.set_axis(d["snapshots"], axis=0)
    out.generators_t.p = disp.reindex(columns=out.generators.index,
                                      fill_value=0.0)
    out.meta = dict(out.meta, redispatch=meta)
    out.export_to_netcdf(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    cfg = dict(snakemake.params.redispatch)  # noqa: F821
    solving = snakemake.params.solving  # noqa: F821
    solver = dict(
        solver_name=solving["solver"]["name"],
        solver_options=solving.get("solver_options", {}).get(
            solving["solver"].get("options", ""), {}))
    stage1 = cfg.get("stage1", "ntc")

    n = pypsa.Network(snakemake.input.network)  # noqa: F821

    if stage1 == "fbmc":
        s1 = pypsa.Network(snakemake.input.stage1)  # noqa: F821
        fmeta = s1.meta.get("fbmc") or {}
        # align window and zone map with the artifact that produced the
        # schedule — its meta is authoritative
        if fmeta.get("window"):
            w0 = pd.Timestamp(fmeta["window"][0])
            w1 = pd.Timestamp(fmeta["window"][-1])
            cfg["snapshots"] = {"start": str(w0),
                                "end": str(w1 + pd.Timedelta(hours=1))}
        if fmeta.get("zones"):
            cfg["zones"] = {"mode": "busmap", "busmap": fmeta["zones"]}
        d = extract_market_data(n, cfg)
        g_star, fdc_star, market_cost = stage1_from_fbmc(d, s1)
    elif stage1 == "ntc":
        d = extract_market_data(n, cfg)
        ntcs = make_ntcs(d, float(cfg.get("ntc_haircut", 0.7)))
        res = solve_zonal_ntc(d, ntcs, **solver)
        g_star, fdc_star, market_cost = res["g"], res["fdc"], res["cost"]
    else:
        raise ValueError(f"redispatch.stage1 must be ntc|fbmc, "
                         f"got {stage1!r}")

    ptdf = compute_ptdf(d["nodes"], d["lines"])
    rd = solve_redispatch(
        d, ptdf, g_star, fdc_star,
        beta=resolve_beta(cfg, d),
        cross_zonal_cap=cfg.get("cross_zonal_cap"), **solver)
    meta = summarize(d, ptdf, g_star, fdc_star, rd, stage1, market_cost,
                     cfg)

    logger.info("redispatch after %s stage 1: volume %.0f MWh, cost %.0f "
                "EUR, overloads %.0f -> %.0f MWh, cross-zonal share %.2f",
                stage1, meta["volume_mwh"], meta["rd_cost"],
                meta["overload_pre_mwh"], meta["overload_post_mwh"],
                meta["cross_zonal_share"])

    export_network(n, d, rd, meta, snakemake.output.network)  # noqa: F821
    flat = {k: v for k, v in meta.items()
            if isinstance(v, (int, float, str))}
    pd.DataFrame([flat]).to_csv(snakemake.output.summary,  # noqa: F821
                                index=False)
