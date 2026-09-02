# Redispatch — algorithmic core.
#
# Shipped by the zygon methods payload `redispatch` (cookbooks/methods/
# redispatch/payload/). Implements the remedial-action stage of Thomassen
# et al. (2025) §3.4: market schedule fixed, paid upward/downward
# deviations restore feasibility on the full nodal network, objective =
# remedial cost PLUS a volume penalty, cross-zonal countertrading capped.
#
# Deliberately self-contained: the extraction / PTDF / NTC-clearing
# substrate is a trimmed DUPLICATE of the flow-based-market-coupling
# payload's core (method payloads must be file-disjoint to compose in one
# bundle), so this method verifies standalone — an NTC stage 1 is built
# here when no FBMC artifact is supplied.

import logging

import linopy
import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

VRE_CARRIERS = {"onwind", "offwind-ac", "offwind-dc", "offwind-float",
                "solar", "solar-hsat", "ror"}
THERMAL_CARRIERS = {"CCGT", "OCGT", "coal", "lignite", "oil", "nuclear",
                    "biomass", "waste", "geothermal"}


# ── data extraction (duplicate of fbmc_core, trimmed) ────────────────────────

def _largest_ac_component(buses, lines):
    parent = {b: b for b in buses}

    def find(b):
        while parent[b] != b:
            parent[b] = parent[parent[b]]
            b = parent[b]
        return b

    for _, ln in lines.iterrows():
        if ln.bus0 in parent and ln.bus1 in parent:
            parent[find(ln.bus0)] = find(ln.bus1)
    comps = {}
    for b in buses:
        comps.setdefault(find(b), []).append(b)
    return pd.Index(max(comps.values(), key=len))


def _zone_map(buses_df, zcfg):
    mode = zcfg.get("mode", "country")
    if mode == "busmap":
        busmap = zcfg.get("busmap") or {}
        missing = [b for b in buses_df.index if b not in busmap]
        if missing:
            raise ValueError(f"redispatch zones.busmap misses: {missing}")
        return pd.Series({b: str(busmap[b]) for b in buses_df.index})
    if mode == "country":
        return buses_df.country.astype(str)
    if mode == "split":
        n = int(zcfg.get("n", 2))
        zones = pd.Series(index=buses_df.index, dtype=object)
        for country, grp in buses_df.groupby("country"):
            if len(grp) < n:
                labels = np.zeros(len(grp), dtype=int)
            else:
                labels = pd.qcut(grp.y.rank(method="first"), n,
                                 labels=False)
            zones.loc[grp.index] = [f"{country}{int(k)}" for k in labels]
        return zones
    raise ValueError(f"unknown zones.mode: {mode!r}")


def extract_market_data(n, cfg):
    """One snapshot window, power-only, existing fleet, largest AC mesh +
    commissioned DC links. Identical semantics to the FBMC payload's
    extraction so a stage-1 schedule maps 1:1 onto this dataset."""
    snaps = n.snapshots[
        (n.snapshots >= pd.Timestamp(cfg["snapshots"]["start"]))
        & (n.snapshots < pd.Timestamp(cfg["snapshots"]["end"]))]
    if len(snaps) == 0:
        raise ValueError(f"snapshot window {cfg['snapshots']} empty")
    t = pd.Index(range(len(snaps)), name="t")

    ac_buses = n.buses.index[n.buses.carrier == "AC"]
    lines_all = n.lines[(n.lines.x > 0)
                        & n.lines.bus0.isin(ac_buses)
                        & n.lines.bus1.isin(ac_buses)]
    keep = _largest_ac_component(ac_buses, lines_all)
    nodes = n.buses.loc[keep, ["x", "y", "country"]].copy()
    nodes["zone"] = _zone_map(nodes, cfg.get("zones") or {})

    lines = lines_all[lines_all.bus0.isin(keep)
                      & lines_all.bus1.isin(keep)].copy()
    lines["fmax"] = lines.s_nom * lines.s_max_pu \
        * float(cfg.get("line_scaling", 1.0))
    lines = lines[["bus0", "bus1", "x", "fmax"]]
    lines["zone0"] = nodes.zone[lines.bus0].values
    lines["zone1"] = nodes.zone[lines.bus1].values
    lines["is_tie"] = lines.zone0 != lines.zone1

    dc = n.links[(n.links.carrier == "DC") & (n.links.p_nom > 0)
                 & n.links.bus0.isin(keep) & n.links.bus1.isin(keep)]
    dc = dc[["bus0", "bus1", "p_nom"]].rename(columns={"p_nom": "fmax"})

    gens = n.generators[(n.generators.p_nom > 0)
                        & n.generators.bus.isin(keep)
                        & (n.generators.carrier != "load shedding")]
    gens = gens[["bus", "carrier", "p_nom", "marginal_cost"]].rename(
        columns={"bus": "node", "p_nom": "cap", "marginal_cost": "mc"})
    avail = n.get_switchable_as_dense("Generator", "p_max_pu") \
        .loc[snaps, gens.index]
    mc = n.get_switchable_as_dense("Generator", "marginal_cost") \
        .loc[snaps, gens.index]

    load = n.loads_t.p_set.loc[snaps]
    load = load.T.groupby(n.loads.bus.loc[load.columns]).sum() \
        .reindex(keep).fillna(0.0)
    load.columns = t

    voll = float(cfg.get("voll", 3000.0))
    shed = pd.DataFrame({"node": keep, "carrier": "load shedding",
                         "cap": 1.0, "mc": voll},
                        index=pd.Index([f"shed {b}" for b in keep]))
    gens = pd.concat([gens, shed])

    avail_all = pd.DataFrame(0.0, index=gens.index, columns=t)
    avail_all.loc[avail.columns] = avail.T.values
    avail_all.loc[shed.index] = load.values
    mc_all = pd.DataFrame(0.0, index=gens.index, columns=t)
    mc_all.loc[mc.columns] = mc.T.values
    mc_all.loc[shed.index] = voll
    gens["zone"] = nodes.zone[gens.node].values

    zones = sorted(nodes.zone.unique())
    if len(zones) < 2:
        raise ValueError("redispatch needs >= 2 zones; check zones config")
    for df in (nodes, lines, dc, gens, load, avail_all, mc_all):
        df.index.name = None
    return dict(nodes=nodes, lines=lines, dc=dc, gens=gens, load=load,
                avail=avail_all, mc=mc_all, t=t, snapshots=snaps,
                zones=zones)


# ── PTDF and flows (duplicate of fbmc_core) ──────────────────────────────────

def compute_ptdf(nodes, lines):
    N = len(nodes)
    nidx = {b: i for i, b in enumerate(nodes.index)}
    K = np.zeros((N, len(lines)))
    for li, (_, ln) in enumerate(lines.iterrows()):
        K[nidx[ln.bus0], li] = 1.0
        K[nidx[ln.bus1], li] = -1.0
    b = 1.0 / lines.x.values
    Bbus = K @ np.diag(b) @ K.T
    keep = list(range(1, N))
    Binv = np.zeros((N, N))
    Binv[np.ix_(keep, keep)] = np.linalg.inv(Bbus[np.ix_(keep, keep)])
    return pd.DataFrame(np.diag(b) @ K.T @ Binv,
                        index=lines.index, columns=nodes.index)


def dc_injection(d, fdc):
    inj = pd.DataFrame(0.0, index=d["nodes"].index, columns=d["t"])
    for li, (link, ln) in enumerate(d["dc"].iterrows()):
        flow = np.asarray(fdc)[li] if len(d["dc"]) else 0.0
        inj.loc[ln.bus0] -= flow
        inj.loc[ln.bus1] += flow
    return inj


def nodal_net_positions(d, g):
    npn = pd.DataFrame(0.0, index=d["nodes"].index, columns=d["t"])
    gen_by_node = g.groupby(d["gens"].node).sum()
    npn.loc[gen_by_node.index] += gen_by_node.values
    return npn - d["load"]


def physical_flows(d, ptdf, g, fdc):
    inj = nodal_net_positions(d, g) + dc_injection(d, fdc)
    return pd.DataFrame(ptdf.values @ inj.values,
                        index=ptdf.index, columns=d["t"])


def overloads(d, ptdf, g, fdc):
    f = physical_flows(d, ptdf, g, fdc)
    ov = f.abs().sub(d["lines"].fmax, axis=0).clip(lower=0.0)
    return f, ov


def dispatch_cost(d, g):
    return float((d["mc"].values * g.values).sum())


# ── NTC stage 1 (duplicate, for standalone use) ──────────────────────────────

def make_ntcs(d, haircut):
    """NTC per directed zone pair = haircut * summed tie thermal capacity,
    DC capacity folded into its border (standard hybrid coupling — the
    stage-1 shape when no FBMC artifact is supplied)."""
    cap = {}
    for _, ln in d["lines"][d["lines"].is_tie].iterrows():
        for pair in (f"{ln.zone0}>{ln.zone1}", f"{ln.zone1}>{ln.zone0}"):
            cap[pair] = cap.get(pair, 0.0) + ln.fmax
    zone = d["nodes"].zone
    for _, ln in d["dc"].iterrows():
        z0, z1 = zone[ln.bus0], zone[ln.bus1]
        if z0 == z1:
            continue
        for pair in (f"{z0}>{z1}", f"{z1}>{z0}"):
            cap[pair] = cap.get(pair, 0.0) + ln.fmax
    return pd.Series({k: haircut * v for k, v in cap.items()}).sort_index()


def _solve(m, solver_name, solver_options=None):
    kwargs = dict(solver_options or {})
    if solver_name in ("gurobi", "highs"):
        kwargs.setdefault("output_flag" if solver_name == "highs"
                          else "OutputFlag", 0)
    status, condition = m.solve(solver_name=solver_name, **kwargs)
    if status != "ok":
        raise RuntimeError(f"solve failed: {status}/{condition}")


def solve_zonal_ntc(d, ntc, solver_name="highs", solver_options=None):
    """Zonal transport-model clearing with fixed bilateral caps — the
    market whose infeasible schedule redispatch then repairs."""
    gens, zones, t = d["gens"], d["zones"], d["t"]
    m = linopy.Model()
    upper = xr.DataArray(d["avail"].values * gens.cap.values[:, None],
                         coords={"gen": gens.index, "t": t},
                         dims=["gen", "t"])
    g = m.add_variables(lower=0, upper=upper, name="g")
    mc = xr.DataArray(d["mc"].values, coords={"gen": gens.index, "t": t},
                      dims=["gen", "t"])

    Mzg = xr.DataArray(
        (gens.zone.values[None, :] == np.array(zones)[:, None]) * 1.0,
        coords={"zone": zones, "gen": gens.index}, dims=["zone", "gen"])
    load_z = d["load"].groupby(d["nodes"].zone).sum().loc[zones]
    loadzx = xr.DataArray(load_z.values, coords={"zone": zones, "t": t},
                          dims=["zone", "t"])
    pairs = list(ntc.index)
    if not pairs:
        raise ValueError("no NTC pairs — is every bus in one zone?")
    ntc_up = xr.DataArray(np.repeat(ntc.values[:, None], len(t), 1),
                          coords={"pair": pairs, "t": t},
                          dims=["pair", "t"])
    ex = m.add_variables(lower=0, upper=ntc_up, name="ex")
    Aout = xr.DataArray(np.array([[p.split(">")[0] == z for p in pairs]
                                  for z in zones]) * 1.0,
                        coords={"zone": zones, "pair": pairs},
                        dims=["zone", "pair"])
    Ain = xr.DataArray(np.array([[p.split(">")[1] == z for p in pairs]
                                 for z in zones]) * 1.0,
                       coords={"zone": zones, "pair": pairs},
                       dims=["zone", "pair"])
    npos = (Aout * ex).sum("pair") - (Ain * ex).sum("pair")
    m.add_constraints((Mzg * g).sum("gen") - npos == loadzx, name="zbal")
    m.add_objective((mc * g).sum())
    _solve(m, solver_name, solver_options)
    return dict(g=g.solution.to_pandas(),
                fdc=pd.DataFrame(0.0, index=d["dc"].index, columns=t),
                price=m.constraints["zbal"].dual.to_pandas(),
                cost=float(m.objective.value))


# ── the redispatch stage (§3.4) ──────────────────────────────────────────────

def solve_redispatch(d, ptdf, g_star, fdc_star, beta=1.0,
                     cross_zonal_cap=None, solver_name="highs",
                     solver_options=None):
    """Market outcome fixed; the TSO buys R_up/R_down so physical flows
    respect line ratings.  min  MC*R_up - MC*R_down + beta*(R_up+R_down).
    beta MUST be positive — a pure-cost objective quietly re-derives the
    nodal optimum and reports congestion as free (the corpus's no-op
    failure). `cross_zonal_cap` bounds the share of remedial volume
    procured outside the zones touching an overloaded line
    (countertrading; both JRC studies use 0.3)."""
    gens, lines, t = d["gens"], d["lines"], d["t"]
    m = linopy.Model()
    upper = xr.DataArray(d["avail"].values * gens.cap.values[:, None],
                         coords={"gen": gens.index, "t": t},
                         dims=["gen", "t"])
    gstar = xr.DataArray(g_star.values,
                         coords={"gen": gens.index, "t": t},
                         dims=["gen", "t"])
    rup = m.add_variables(lower=0, upper=(upper - gstar).clip(min=0),
                          name="rup")
    rdn = m.add_variables(lower=0, upper=gstar.clip(min=0), name="rdn")

    m.add_constraints(rup.sum("gen") - rdn.sum("gen") == 0, name="bal")

    f_mkt = physical_flows(d, ptdf, g_star, fdc_star.values)
    Pngx = xr.DataArray(ptdf[gens.node].values,
                        coords={"line": lines.index, "gen": gens.index},
                        dims=["line", "gen"])
    df = (Pngx * (rup - rdn)).sum("gen")
    fmaxx = xr.DataArray(lines.fmax.values,
                         coords={"line": lines.index}, dims=["line"])
    fmktx = xr.DataArray(f_mkt.values,
                         coords={"line": lines.index, "t": t},
                         dims=["line", "t"])
    m.add_constraints(df <= fmaxx - fmktx, name="lim_up")
    m.add_constraints(df >= -fmaxx - fmktx, name="lim_dn")

    congested = set()
    if cross_zonal_cap is not None:
        _, ov = overloads(d, ptdf, g_star, fdc_star.values)
        hot = ov.sum(axis=1)[ov.sum(axis=1) > 0].index
        congested = set(d["lines"].loc[hot, ["zone0", "zone1"]]
                        .values.ravel())
        outside = gens.index[~gens.zone.isin(congested)]
        if len(outside) and len(congested):
            out_sel = (rup.sel(gen=list(outside))
                       + rdn.sel(gen=list(outside))).sum()
            m.add_constraints(
                out_sel - float(cross_zonal_cap) * (rup + rdn).sum() <= 0,
                name="cross_zonal_cap")

    mc = xr.DataArray(d["mc"].values,
                      coords={"gen": gens.index, "t": t}, dims=["gen", "t"])
    m.add_objective((mc * rup).sum() - (mc * rdn).sum()
                    + beta * (rup + rdn).sum())
    _solve(m, solver_name, solver_options)
    rup_s = rup.solution.to_pandas()
    rdn_s = rdn.solution.to_pandas()
    g_final = g_star + rup_s - rdn_s
    outside_idx = gens.index[~gens.zone.isin(congested)] if congested \
        else pd.Index([])
    total = float((rup_s + rdn_s).values.sum())
    outside_vol = float((rup_s.loc[outside_idx]
                         + rdn_s.loc[outside_idx]).values.sum()) \
        if len(outside_idx) else 0.0
    return dict(rup=rup_s, rdn=rdn_s, g=g_final,
                rd_cost=float((d["mc"].values
                               * (rup_s - rdn_s).values).sum()),
                volume=total,
                volume_up=float(rup_s.values.sum()),
                volume_dn=float(rdn_s.values.sum()),
                cross_zonal_share=(outside_vol / total if total > 0
                                   else 0.0),
                congested_zones=sorted(congested))
