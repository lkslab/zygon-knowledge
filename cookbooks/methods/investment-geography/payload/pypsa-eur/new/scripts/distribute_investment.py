# Investment geography — snakemake entry.
#
# Shipped by the zygon methods payload `investment-geography`. Implements
# Thomassen et al. (2025) §3.2: renewable capacity TOTALS are fixed per
# country and technology (auction targets); WHERE inside the country the
# capacity lands is a blend of two distributions, mixed by the auction
# effectiveness eta (calibrated to 0.6 against German zip-code deployment
# in the paper):
#
#   auction: cost-optimal siting — a copperplate-per-country expansion LP
#            (the market WITHOUT locational signals sees no intra-zonal
#            grid, so only capacity factors and potentials steer siting)
#   even:    the same share of AVAILABLE LAND used in every cell —
#            capacity proportional to p_nom_max (availability x area at
#            fixed MW/km2), the capacity-spreading counterfactual
#
#   Cap = eta * Cap_auction + (1 - eta) * Cap_even
#
# Runs on a config-selected snapshot window of the electricity network
# (existing fleet + extendable candidates). Output: the sliced network
# with the blended NEW capacities written as fixed generators, plus a
# n.meta['investment_geography'] summary (targets, all three
# distributions, concentration indices) the success metrics consume.

import logging
import sys
from pathlib import Path

import linopy
import numpy as np
import pandas as pd
import pypsa
import xarray as xr

logger = logging.getLogger(__name__)


def slice_window(n, cfg):
    snaps = n.snapshots[
        (n.snapshots >= pd.Timestamp(cfg["snapshots"]["start"]))
        & (n.snapshots < pd.Timestamp(cfg["snapshots"]["end"]))]
    if len(snaps) == 0:
        raise ValueError(f"window {cfg['snapshots']} selects no snapshots")
    return snaps


def candidate_frame(n, techs):
    """Extendable candidates of the target technologies: per bus(-bin)
    potential, capital cost, and country."""
    g = n.generators
    cand = g[(g.carrier.isin(techs)) & g.p_nom_extendable
             & (g.p_nom_max > 0) & np.isfinite(g.p_nom_max)]
    out = cand[["bus", "carrier", "p_nom_max", "capital_cost",
                "marginal_cost"]].copy()
    out["country"] = n.buses.country[out.bus].values
    out.index.name = None
    return out


def solve_auction(n, snaps, cand, targets, solver_name, solver_options):
    """Cost-optimal siting under per-country/technology capacity targets,
    copperplate per country (no intra-zonal grid — the no-locational-
    signals market). Existing fleet dispatches alongside the candidates;
    load shedding keeps the LP feasible. Window opex is scaled to a full
    year so capex/energy-value trade off sensibly."""
    scale = 8760.0 / len(snaps)
    g_all = n.generators[(n.generators.p_nom > 0)
                         & (n.generators.carrier != "load shedding")]
    avail_ex = n.get_switchable_as_dense("Generator", "p_max_pu") \
        .loc[snaps, g_all.index]
    mc_ex = n.get_switchable_as_dense("Generator", "marginal_cost") \
        .loc[snaps, g_all.index]
    avail_c = n.get_switchable_as_dense("Generator", "p_max_pu") \
        .loc[snaps, cand.index]

    countries = sorted(cand.country.unique())
    bus_country = n.buses.country
    loads = n.loads_t.p_set.loc[snaps]
    load_c = loads.T.groupby(
        bus_country[n.loads.bus.loc[loads.columns]].values).sum() \
        .reindex(countries).fillna(0.0)

    t = pd.Index(range(len(snaps)), name="t")
    m = linopy.Model()
    pnew = m.add_variables(
        lower=0, upper=xr.DataArray(cand.p_nom_max.values,
                                    coords={"cand": cand.index.values},
                                    dims=["cand"]), name="pnew")
    gc = m.add_variables(
        lower=0, coords=[pd.Index(cand.index.values, name="cand"), t],
        name="gc")
    upper_ex = xr.DataArray(
        avail_ex.T.values * g_all.p_nom.values[:, None],
        coords={"gen": g_all.index.values, "t": t}, dims=["gen", "t"])
    ge = m.add_variables(lower=0, upper=upper_ex, name="ge")
    shed = m.add_variables(
        lower=0,
        upper=xr.DataArray(load_c.values,
                           coords={"country": countries, "t": t},
                           dims=["country", "t"]), name="shed")

    availc_x = xr.DataArray(avail_c.T.values,
                            coords={"cand": cand.index.values, "t": t},
                            dims=["cand", "t"])
    m.add_constraints(gc - availc_x * pnew <= 0, name="cand_avail")

    Mce = xr.DataArray(
        (bus_country[g_all.bus].values[None, :]
         == np.array(countries)[:, None]) * 1.0,
        coords={"country": countries, "gen": g_all.index.values},
        dims=["country", "gen"])
    Mcc = xr.DataArray(
        (cand.country.values[None, :]
         == np.array(countries)[:, None]) * 1.0,
        coords={"country": countries, "cand": cand.index.values},
        dims=["country", "cand"])
    loadx = xr.DataArray(load_c.values,
                         coords={"country": countries, "t": t},
                         dims=["country", "t"])
    m.add_constraints((Mce * ge).sum("gen") + (Mcc * gc).sum("cand")
                      + shed == loadx, name="cbal")

    for (country, tech), target in targets.items():
        sel = cand.index[(cand.country == country)
                         & (cand.carrier == tech)]
        if not len(sel):
            raise ValueError(f"no candidates for {country}/{tech}")
        cap = float(cand.p_nom_max[sel].sum())
        if target > cap:
            raise ValueError(f"target {target} MW > potential {cap:.0f} "
                             f"MW for {country}/{tech}")
        m.add_constraints(pnew.sel(cand=list(sel)).sum() == float(target),
                          name=f"target_{country}_{tech}")

    capex = xr.DataArray(cand.capital_cost.values,
                         coords={"cand": cand.index.values}, dims=["cand"])
    mcex = xr.DataArray(mc_ex.T.values,
                        coords={"gen": g_all.index.values, "t": t},
                        dims=["gen", "t"])
    mcc = xr.DataArray(cand.marginal_cost.values,
                       coords={"cand": cand.index.values}, dims=["cand"])
    voll = 3000.0
    m.add_objective((capex * pnew).sum()
                    + scale * ((mcex * ge).sum() + (mcc * gc).sum()
                               + voll * shed.sum()))
    kwargs = dict(solver_options or {})
    if solver_name in ("gurobi", "highs"):
        kwargs.setdefault("output_flag" if solver_name == "highs"
                          else "OutputFlag", 0)
    status, cond = m.solve(solver_name=solver_name, **kwargs)
    if status != "ok":
        raise RuntimeError(f"auction LP failed: {status}/{cond}")
    return pnew.solution.to_pandas()


def even_spread(cand, targets):
    """Capacity proportional to available land: the same share of each
    cell's potential is used everywhere in the country (p_nom_max is
    availability x area at fixed MW/km2, so weight by it)."""
    cap = pd.Series(0.0, index=cand.index)
    for (country, tech), target in targets.items():
        sel = cand.index[(cand.country == country)
                         & (cand.carrier == tech)]
        w = cand.p_nom_max[sel]
        cap.loc[sel] = float(target) * w / w.sum()
    return cap


def hhi(cap, cand, targets):
    """Capacity-share Herfindahl per (country, tech), averaged — the
    concentration measure the eta blend must sit between."""
    vals = []
    for (country, tech), target in targets.items():
        sel = cand.index[(cand.country == country)
                         & (cand.carrier == tech)]
        s = cap[sel] / max(float(target), 1e-9)
        vals.append(float((s ** 2).sum()))
    return float(np.mean(vals))


def parse_targets(cfg):
    targets = {}
    for country, techs in (cfg.get("targets") or {}).items():
        for tech, mw in techs.items():
            targets[(str(country), str(tech))] = float(mw)
    if not targets:
        raise ValueError("investment_geography.targets is empty")
    return targets


def export(n, snaps, cand, cap_blend, meta, path):
    out = n.copy(snapshots=snaps)
    named = {f"{i} invgeo": v for i, v in cap_blend.items()}
    add_many = out.madd if hasattr(out, "madd") else out.add
    add_many("Generator", pd.Index(named.keys()),
             bus=cand.bus.values, carrier=cand.carrier.values,
             p_nom=list(named.values()), p_nom_extendable=False,
             capital_cost=cand.capital_cost.values,
             marginal_cost=cand.marginal_cost.values)
    out.meta = dict(out.meta, investment_geography=meta)
    out.export_to_netcdf(path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    cfg = dict(snakemake.params.invgeo)  # noqa: F821
    solving = snakemake.params.solving  # noqa: F821
    solver_name = solving["solver"]["name"]
    solver_options = solving.get("solver_options", {}).get(
        solving["solver"].get("options", ""), {})

    n = pypsa.Network(snakemake.input.network)  # noqa: F821
    snaps = slice_window(n, cfg)
    targets = parse_targets(cfg)
    techs = sorted({tech for _, tech in targets})
    cand = candidate_frame(n, techs)
    eta = float(cfg.get("auction_effectiveness", 0.6))

    cap_auct = solve_auction(n, snaps, cand, targets, solver_name,
                             solver_options)
    cap_even = even_spread(cand, targets)
    cap_blend = eta * cap_auct + (1.0 - eta) * cap_even

    target_err = max(
        abs(float(cap_blend[cand.index[(cand.country == c)
                                       & (cand.carrier == t)]].sum()) - v)
        for (c, t), v in targets.items())
    affine_err = float(
        (cap_blend - (eta * cap_auct + (1.0 - eta) * cap_even))
        .abs().max())
    meta = dict(
        eta=eta,
        target_error_mw=target_err,
        blend_affine_error_mw=affine_err,
        targets={f"{c}|{t}": v for (c, t), v in targets.items()},
        auction={k: float(v) for k, v in cap_auct.items()},
        even={k: float(v) for k, v in cap_even.items()},
        blend={k: float(v) for k, v in cap_blend.items()},
        hhi_auction=hhi(cap_auct, cand, targets),
        hhi_even=hhi(cap_even, cand, targets),
        hhi_blend=hhi(cap_blend, cand, targets),
        window=[str(snaps[0]), str(snaps[-1])],
        technologies=techs,
    )
    logger.info("investment geography: eta=%.2f, HHI auction %.3f >= "
                "blend %.3f >= even %.3f",
                eta, meta["hhi_auction"], meta["hhi_blend"],
                meta["hhi_even"])

    export(n, snaps, cand, cap_blend, meta,
           snakemake.output.network)  # noqa: F821
    rows = pd.DataFrame({"auction": cap_auct, "even": cap_even,
                         "blend": cap_blend,
                         "bus": cand.bus, "carrier": cand.carrier,
                         "country": cand.country})
    rows.to_csv(snakemake.output.summary)  # noqa: F821
