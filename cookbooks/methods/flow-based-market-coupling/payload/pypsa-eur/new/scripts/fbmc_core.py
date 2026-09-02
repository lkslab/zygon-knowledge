# Flow-based market coupling — algorithmic core.
#
# Shipped by the zygon methods payload `flow-based-market-coupling`
# (cookbooks/methods/flow-based-market-coupling/payload/). Implements the
# zonal market-clearing methodology of Thomassen et al. (2025), JRC
# "Locational price signals in Europe", §3.3 (FBMC) and §3.3.1 (optimized
# GSK), on top of an arbitrary solved-or-prepared PyPSA network:
#
#   extract_market_data  pypsa.Network -> plain dispatch dataset (one day,
#                        power-only, existing fleet, AC mesh + DC links)
#   compute_ptdf         DC load-flow sensitivities, slack column zero
#   solve_nodal          theta-formulation nodal LMP benchmark
#   solve_zonal          one clearing model, two constraint sets (ntc|fbmc)
#   compute_gsk          optimized (two-run) / capacity / conventional / flat
#   compute_fb_params    zonal PTDFs, PTDF_DC, F0 (loop flows), RAM +/- FRM
#   solve_redispatch     cost + volume-penalty remedial-action stage (§3.4)
#
# Everything operates on plain pandas/numpy/linopy objects so the same core
# runs unchanged against pypsa-eur and pypsa-earth networks. No file I/O in
# this module; the snakemake entry scripts own reading/writing.

import logging

import linopy
import numpy as np
import pandas as pd
import xarray as xr

logger = logging.getLogger(__name__)

# carriers considered dispatchable for the "conventional" (ERAA-style) GSK
CONVENTIONAL_CARRIERS = {
    "CCGT", "OCGT", "coal", "lignite", "oil", "nuclear", "biomass",
    "waste", "geothermal", "ror", "hydro",
}


# ── data extraction ──────────────────────────────────────────────────────────

def _largest_ac_component(buses, lines):
    """Bus index of the largest connected component of the AC graph."""
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
    """bus -> zone label. Modes: country (one zone per country attribute),
    split (latitude quantile split into n zones per country), busmap
    (explicit mapping from config)."""
    mode = zcfg.get("mode", "country")
    if mode == "busmap":
        busmap = zcfg.get("busmap") or {}
        missing = [b for b in buses_df.index if b not in busmap]
        if missing:
            raise ValueError(f"fbmc.zones.busmap misses buses: {missing}")
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
    raise ValueError(f"unknown fbmc.zones.mode: {mode!r}")


def extract_market_data(n, cfg):
    """Reduce a pypsa network to the plain dispatch dataset the market
    models run on: one snapshot window, power-only, existing fleet
    (p_nom > 0), the meshed AC grid (x > 0 lines of the largest component)
    and any commissioned DC links inside it. Storage is excluded (frozen)
    — the Thomassen market stage handles it, this port's v1 does not."""
    snaps = n.snapshots[(n.snapshots >= pd.Timestamp(cfg["snapshots"]["start"]))
                        & (n.snapshots < pd.Timestamp(cfg["snapshots"]["end"]))]
    if len(snaps) == 0:
        raise ValueError(
            f"fbmc.snapshots window {cfg['snapshots']} selects no snapshots "
            f"of {n.snapshots[0]}..{n.snapshots[-1]}")
    t = pd.Index(range(len(snaps)), name="t")

    ac_buses = n.buses.index[n.buses.carrier == "AC"]
    lines_all = n.lines[(n.lines.x > 0)
                        & n.lines.bus0.isin(ac_buses)
                        & n.lines.bus1.isin(ac_buses)]
    keep = _largest_ac_component(ac_buses, lines_all)
    if len(keep) < len(ac_buses):
        logger.warning("dropping %d AC buses outside the largest synchronous "
                       "component", len(ac_buses) - len(keep))
    nodes = n.buses.loc[keep, ["x", "y", "country"]].copy()
    nodes["zone"] = _zone_map(nodes, cfg.get("zones") or {})

    lines = lines_all[lines_all.bus0.isin(keep)
                      & lines_all.bus1.isin(keep)].copy()
    scaling = float(cfg.get("line_scaling", 1.0))
    lines["fmax"] = lines.s_nom * lines.s_max_pu * scaling
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

    # load shedding at VOLL: cap=1 generators whose availability is the
    # nodal load — keeps every LP feasible and prices scarcity
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
        raise ValueError("FBMC needs >= 2 zones; check fbmc.zones")
    # unnamed indexes: pypsa's 'name'-labelled indexes would otherwise
    # collide with explicit xarray dimension names in the linopy models
    for df in (nodes, lines, dc, gens, load, avail_all, mc_all):
        df.index.name = None
    return dict(nodes=nodes, lines=lines, dc=dc, gens=gens, load=load,
                avail=avail_all, mc=mc_all, t=t, snapshots=snaps,
                zones=zones)


# ── PTDF and flows ───────────────────────────────────────────────────────────

def compute_ptdf(nodes, lines):
    """DC load-flow sensitivities (L x N), slack = first bus, its column
    zero. flow_l = sum_n PTDF_{l,n} * injection_n."""
    N, L = len(nodes), len(lines)
    nidx = {b: i for i, b in enumerate(nodes.index)}
    K = np.zeros((N, L))
    for li, (_, ln) in enumerate(lines.iterrows()):
        K[nidx[ln.bus0], li] = 1.0
        K[nidx[ln.bus1], li] = -1.0
    b = 1.0 / lines.x.values
    Bbus = K @ np.diag(b) @ K.T
    keep = list(range(1, N))
    Binv = np.zeros((N, N))
    Binv[np.ix_(keep, keep)] = np.linalg.inv(Bbus[np.ix_(keep, keep)])
    ptdf = np.diag(b) @ K.T @ Binv
    return pd.DataFrame(ptdf, index=lines.index, columns=nodes.index)


def dc_injection(d, fdc):
    """Nodal injections (N x T) implied by DC link flows (bus0 -> bus1)."""
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
    """AC line flows (L x T) implied by a dispatch and DC flows."""
    inj = nodal_net_positions(d, g) + dc_injection(d, fdc)
    return pd.DataFrame(ptdf.values @ inj.values,
                        index=ptdf.index, columns=d["t"])


def overloads(d, ptdf, g, fdc):
    f = physical_flows(d, ptdf, g, fdc)
    ov = f.abs().sub(d["lines"].fmax, axis=0).clip(lower=0.0)
    return f, ov


def dispatch_cost(d, g):
    return float((d["mc"].values * g.values).sum())


# ── NTCs and CNECs ───────────────────────────────────────────────────────────

def make_ntcs(d, haircut, hybrid_coupling="advanced"):
    """NTC per directed zone pair = haircut * summed tie thermal capacity.
    Under STANDARD hybrid coupling, DC capacity is folded into the NTC of
    its border; under ADVANCED it stays an explicit market variable."""
    cap = {}
    for _, ln in d["lines"][d["lines"].is_tie].iterrows():
        for pair in (f"{ln.zone0}>{ln.zone1}", f"{ln.zone1}>{ln.zone0}"):
            cap[pair] = cap.get(pair, 0.0) + ln.fmax
    if hybrid_coupling == "standard":
        zone = d["nodes"].zone
        for _, ln in d["dc"].iterrows():
            z0, z1 = zone[ln.bus0], zone[ln.bus1]
            if z0 == z1:
                continue
            for pair in (f"{z0}>{z1}", f"{z1}>{z0}"):
                cap[pair] = cap.get(pair, 0.0) + ln.fmax
    return pd.Series({k: haircut * v for k, v in cap.items()}).sort_index()


def select_cnecs(d, ptdf, threshold, ties_always=True):
    """Critical network elements: every tie line (if ties_always) plus any
    line whose flow is sensitive to a cross-zonal exchange — max spread of
    capacity-weighted zone-mean PTDFs above `threshold` (industry practice:
    5% zone-to-line sensitivity screen)."""
    nodes = d["nodes"]
    capw = d["gens"][d["gens"].carrier != "load shedding"] \
        .groupby("node").cap.sum().reindex(nodes.index).fillna(0.0)
    zmeans = {}
    for z in d["zones"]:
        zn = nodes.index[nodes.zone == z]
        w = capw[zn]
        w = w / w.sum() if w.sum() > 0 else pd.Series(1 / len(zn), index=zn)
        zmeans[z] = ptdf[zn].values @ w.values
    zm = pd.DataFrame(zmeans, index=ptdf.index)
    spread = zm.max(axis=1) - zm.min(axis=1)
    cnecs = spread[spread > threshold].index
    if ties_always:
        cnecs = cnecs.union(d["lines"].index[d["lines"].is_tie])
    return pd.Index(cnecs)


# ── market clearing ──────────────────────────────────────────────────────────

def _gen_vars(m, d):
    gens, t = d["gens"], d["t"]
    upper = xr.DataArray(d["avail"].values * gens.cap.values[:, None],
                         coords={"gen": gens.index, "t": t},
                         dims=["gen", "t"])
    g = m.add_variables(lower=0, upper=upper, name="g")
    mc = xr.DataArray(d["mc"].values, coords={"gen": gens.index, "t": t},
                      dims=["gen", "t"])
    return g, mc


def _solve(m, solver_name, solver_options=None):
    kwargs = dict(solver_options or {})
    if solver_name in ("gurobi", "highs"):
        kwargs.setdefault("output_flag" if solver_name == "highs"
                          else "OutputFlag", 0)
    status, condition = m.solve(solver_name=solver_name, **kwargs)
    if status != "ok":
        raise RuntimeError(f"solve failed: {status}/{condition}")


def solve_nodal(d, solver_name="highs", solver_options=None):
    """Nodal LMP benchmark: theta-formulation DC-OPF. LMPs are the duals of
    the nodal balance."""
    nodes, lines, gens, t = d["nodes"], d["lines"], d["gens"], d["t"]
    m = linopy.Model()
    g, mc = _gen_vars(m, d)
    theta = m.add_variables(
        coords=[nodes.index.rename("node"), pd.Index(t, name="t")],
        name="theta")
    fmax = xr.DataArray(np.repeat(lines.fmax.values[:, None], len(t), 1),
                        coords={"line": lines.index, "t": t},
                        dims=["line", "t"])
    f = m.add_variables(lower=-fmax, upper=fmax, name="f")

    ndc = len(d["dc"])
    if ndc:
        dcmax = xr.DataArray(
            np.repeat(d["dc"].fmax.values[:, None], len(t), 1),
            coords={"dclink": d["dc"].index, "t": t}, dims=["dclink", "t"])
        fdc = m.add_variables(lower=-dcmax, upper=dcmax, name="fdc")

    A = pd.DataFrame(0.0, index=lines.index, columns=nodes.index)
    for l, ln in lines.iterrows():
        A.loc[l, ln.bus0], A.loc[l, ln.bus1] = 1.0 / ln.x, -1.0 / ln.x
    Ax = xr.DataArray(A.values,
                      coords={"line": lines.index, "node": nodes.index},
                      dims=["line", "node"])
    m.add_constraints(f - (Ax * theta).sum("node") == 0, name="flowdef")
    m.add_constraints(theta.sel(node=nodes.index[0]) == 0, name="slack")

    Mng = xr.DataArray(
        (gens.node.values[None, :] == nodes.index.values[:, None]) * 1.0,
        coords={"node": nodes.index, "gen": gens.index},
        dims=["node", "gen"])
    K = pd.DataFrame(0.0, index=nodes.index, columns=lines.index)
    for l, ln in lines.iterrows():
        K.loc[ln.bus0, l], K.loc[ln.bus1, l] = 1.0, -1.0
    Kx = xr.DataArray(K.values,
                      coords={"node": nodes.index, "line": lines.index},
                      dims=["node", "line"])
    loadx = xr.DataArray(d["load"].values,
                         coords={"node": nodes.index, "t": t},
                         dims=["node", "t"])
    lhs = (Mng * g).sum("gen") - (Kx * f).sum("line")
    if ndc:
        E = pd.DataFrame(0.0, index=nodes.index, columns=d["dc"].index)
        for l, ln in d["dc"].iterrows():
            E.loc[ln.bus0, l] -= 1.0
            E.loc[ln.bus1, l] += 1.0
        Ex = xr.DataArray(E.values,
                          coords={"node": nodes.index, "dclink": d["dc"].index},
                          dims=["node", "dclink"])
        lhs = lhs + (Ex * fdc).sum("dclink")
    m.add_constraints(lhs == loadx, name="nbal")

    m.add_objective((mc * g).sum())
    _solve(m, solver_name, solver_options)
    # all 2-D results follow the (entity x t) convention
    fdc_sol = (fdc.solution.to_pandas() if ndc
               else pd.DataFrame(0.0, index=d["dc"].index, columns=t))
    return dict(g=g.solution.to_pandas(), f=f.solution.to_pandas(),
                fdc=fdc_sol,
                lmp=m.constraints["nbal"].dual.to_pandas(),
                cost=float(m.objective.value))


def solve_zonal(d, mode, ntc=None, fb=None, solver_name="highs",
                solver_options=None):
    """Zonal clearing. mode='ntc': transport model between zones with fixed
    bilateral caps (autarky = ntc * 0). mode='fbmc': zonal net positions
    constrained by the flow-based domain; DC links are explicit market
    variables (advanced hybrid coupling). The GSK never appears here — it
    is baked into fb['zptdf'] offline. Zonal price = dual of the ONE
    aggregated balance per zone."""
    gens, zones, t = d["gens"], d["zones"], d["t"]
    m = linopy.Model()
    g, mc = _gen_vars(m, d)

    Mzg = xr.DataArray(
        (gens.zone.values[None, :] == np.array(zones)[:, None]) * 1.0,
        coords={"zone": zones, "gen": gens.index}, dims=["zone", "gen"])
    load_z = d["load"].groupby(d["nodes"].zone).sum().loc[zones]
    loadzx = xr.DataArray(load_z.values, coords={"zone": zones, "t": t},
                          dims=["zone", "t"])
    zgen = (Mzg * g).sum("gen")

    if mode == "ntc":
        pairs = list(ntc.index)
        if not pairs:
            raise ValueError("no NTC pairs — is every bus in one zone?")
        ntc_up = xr.DataArray(np.repeat(ntc.values[:, None], len(t), 1),
                              coords={"pair": pairs, "t": t},
                              dims=["pair", "t"])
        ex = m.add_variables(lower=0, upper=ntc_up, name="ex")
        Aout = xr.DataArray(
            np.array([[p.split(">")[0] == z for p in pairs]
                      for z in zones]) * 1.0,
            coords={"zone": zones, "pair": pairs}, dims=["zone", "pair"])
        Ain = xr.DataArray(
            np.array([[p.split(">")[1] == z for p in pairs]
                      for z in zones]) * 1.0,
            coords={"zone": zones, "pair": pairs}, dims=["zone", "pair"])
        npos = (Aout * ex).sum("pair") - (Ain * ex).sum("pair")
        m.add_constraints(zgen - npos == loadzx, name="zbal")
        m.add_objective((mc * g).sum())
        _solve(m, solver_name, solver_options)
        np_sol = ((Aout * ex.solution).sum("pair")
                  - (Ain * ex.solution).sum("pair")).to_pandas()
        return dict(g=g.solution.to_pandas(), npos=np_sol,
                    fdc=pd.DataFrame(0.0, index=d["dc"].index, columns=t),
                    price=m.constraints["zbal"].dual.to_pandas(),
                    cost=float(m.objective.value))

    # ---- FBMC ----------------------------------------------------------
    cnecs = fb["cnecs"]
    npv = m.add_variables(coords=[pd.Index(zones, name="zone"),
                                  pd.Index(t, name="t")], name="np")
    ndc = len(d["dc"])
    if ndc:
        dcmax = xr.DataArray(
            np.repeat(d["dc"].fmax.values[:, None], len(t), 1),
            coords={"dclink": d["dc"].index, "t": t}, dims=["dclink", "t"])
        fdc = m.add_variables(lower=-dcmax, upper=dcmax, name="fdc")

    # zonal balance: gen - load = AC net position + net DC exports
    bal = zgen - npv
    if ndc:
        zone = d["nodes"].zone
        Edz = pd.DataFrame(0.0, index=zones, columns=d["dc"].index)
        for l, ln in d["dc"].iterrows():
            Edz.loc[zone[ln.bus0], l] += 1.0   # DC flow leaves start zone
            Edz.loc[zone[ln.bus1], l] -= 1.0   # and enters end zone
        Edzx = xr.DataArray(Edz.values,
                            coords={"zone": zones, "dclink": d["dc"].index},
                            dims=["zone", "dclink"])
        bal = bal - (Edzx * fdc).sum("dclink")
    m.add_constraints(bal == loadzx, name="zbal")
    m.add_constraints(npv.sum("zone") == 0, name="np_closure")

    # CNEC constraints: RAM- <= sum_z zPTDF*NP (+ PTDF_DC*fdc) <= RAM+
    zptdf = xr.DataArray(fb["zptdf"].loc[cnecs].values
                         .reshape(len(cnecs), len(zones), len(t)),
                         coords={"line": cnecs, "zone": zones, "t": t},
                         dims=["line", "zone", "t"])
    fcnec = (zptdf * npv).sum("zone")
    if ndc:
        pdc = xr.DataArray(fb["ptdf_dc"].loc[cnecs].values,
                           coords={"line": cnecs, "dclink": d["dc"].index},
                           dims=["line", "dclink"])
        fcnec = fcnec + (pdc * fdc).sum("dclink")
    ramp = xr.DataArray(fb["ram_pos"].loc[cnecs].values,
                        coords={"line": cnecs, "t": t}, dims=["line", "t"])
    ramn = xr.DataArray(fb["ram_neg"].loc[cnecs].values,
                        coords={"line": cnecs, "t": t}, dims=["line", "t"])
    m.add_constraints(fcnec <= ramp, name="cnec_up")
    m.add_constraints(fcnec >= ramn, name="cnec_dn")

    m.add_objective((mc * g).sum())
    _solve(m, solver_name, solver_options)
    fdc_sol = (fdc.solution.to_pandas() if ndc
               else pd.DataFrame(0.0, index=d["dc"].index, columns=t))
    duals_up = m.constraints["cnec_up"].dual.to_pandas()
    duals_dn = m.constraints["cnec_dn"].dual.to_pandas()
    return dict(g=g.solution.to_pandas(),
                npos=npv.solution.to_pandas(),
                fdc=fdc_sol,
                price=m.constraints["zbal"].dual.to_pandas(),
                cost=float(m.objective.value),
                cnec_dual_up=duals_up, cnec_dual_dn=duals_dn)


# ── GSK (§3.3.1) ─────────────────────────────────────────────────────────────

def compute_gsk(d, run_ntc=None, run_aut=None, variant="optimized",
                eps_mw=50.0):
    """Generator shift keys per node and hour. `optimized` is the paper's
    two-run observed marginal participation with a capacity-weighted
    fallback where a zone's net position barely moves; `capacity` /
    `conventional` are static pro-rata (all gens / dispatchable-only);
    `flat` is equal-per-node."""
    nodes, zones, t = d["nodes"], d["zones"], d["t"]
    gens = d["gens"][d["gens"].carrier != "load shedding"]
    gsk = pd.DataFrame(0.0, index=nodes.index, columns=t)
    fallback_share = pd.Series(0.0, index=zones)

    def static_weights(zn, pool):
        w = pool.groupby("node").cap.sum().reindex(zn).fillna(0.0)
        return w / w.sum() if w.sum() > 0 else \
            pd.Series(1.0 / len(zn), index=zn)

    if variant in ("capacity", "conventional", "flat"):
        for z in zones:
            zn = nodes.index[nodes.zone == z]
            if variant == "flat":
                w = pd.Series(1.0 / len(zn), index=zn)
            else:
                pool = gens if variant == "capacity" else \
                    gens[gens.carrier.isin(CONVENTIONAL_CARRIERS)]
                w = static_weights(zn, pool[pool.zone == z])
            gsk.loc[zn] = np.repeat(w.values[:, None], len(t), 1)
        return gsk, fallback_share

    if variant != "optimized":
        raise ValueError(f"unknown fbmc.gsk.variant: {variant!r}")
    dnp = nodal_net_positions(d, run_ntc["g"]) \
        - nodal_net_positions(d, run_aut["g"])
    for z in zones:
        zn = nodes.index[nodes.zone == z]
        dz = dnp.loc[zn].sum(axis=0)
        w_cap = static_weights(zn, gens[gens.zone == z])
        use_fb = dz.abs() < eps_mw
        fallback_share[z] = float(use_fb.mean())
        for h in t:
            gsk.loc[zn, h] = (w_cap.values if use_fb[h]
                              else (dnp.loc[zn, h] / dz[h]).values)
    return gsk, fallback_share


# ── flow-based parameters (§3.3) ─────────────────────────────────────────────

def compute_fb_params(d, ptdf, gsk, run_aut, frm_frac, minram_frac, cnecs):
    """zPTDF (per line, zone, hour), DC-link PTDFs (advanced hybrid
    coupling), F0 = loop flows of the autarky dispatch, RAM = Fmax -/+ FRM
    - F0 with a minRAM floor guaranteeing a nonempty domain."""
    lines, zones, nodes, t = d["lines"], d["zones"], d["nodes"], d["t"]
    L, Z, T = len(lines), len(zones), len(t)

    zptdf = np.zeros((L, Z, T))
    for zi, z in enumerate(zones):
        zn = nodes.index[nodes.zone == z]
        zptdf[:, zi, :] = ptdf[zn].values @ gsk.loc[zn].values
    zptdf = pd.DataFrame(zptdf.reshape(L, Z * T), index=lines.index)

    ptdf_dc = pd.DataFrame(
        {l: ptdf[ln.bus1] - ptdf[ln.bus0]
         for l, ln in d["dc"].iterrows()},
        index=lines.index, columns=d["dc"].index, dtype=float)

    f0 = physical_flows(d, ptdf, run_aut["g"],
                        np.zeros((len(d["dc"]), T)))

    fmax = d["lines"].fmax
    frm = frm_frac * fmax
    ram_pos = (-f0).add(fmax - frm, axis=0)
    ram_neg = (-f0).add(-fmax + frm, axis=0)
    floor = minram_frac * fmax
    ram_pos = ram_pos.clip(lower=floor, axis=0)
    ram_neg = ram_neg.clip(upper=-floor, axis=0)
    return dict(zptdf=zptdf, ptdf_dc=ptdf_dc, f0=f0,
                ram_pos=ram_pos, ram_neg=ram_neg, cnecs=cnecs)


# ── redispatch (§3.4) ────────────────────────────────────────────────────────

def solve_redispatch(d, ptdf, g_star, fdc_star, beta=1.0,
                     cross_zonal_cap=None, solver_name="highs",
                     solver_options=None):
    """Remedial-action stage: market schedule fixed, paid upward/downward
    deviations restore feasibility on the full network. Objective is
    cost PLUS a volume penalty (beta must exceed zero or the stage can
    re-derive the nodal optimum and report congestion as free). Optional
    cross-zonal cap: at most `cross_zonal_cap` share of total remedial
    volume may be procured outside the overloaded lines' zones (both JRC
    studies use 0.3)."""
    gens, lines, t = d["gens"], d["lines"], d["t"]
    m = linopy.Model()
    upper = xr.DataArray(d["avail"].values * gens.cap.values[:, None],
                         coords={"gen": gens.index, "t": t},
                         dims=["gen", "t"])
    gstar = xr.DataArray(g_star.values,
                         coords={"gen": gens.index, "t": t},
                         dims=["gen", "t"])
    rup = m.add_variables(lower=0, upper=upper - gstar, name="rup")
    rdn = m.add_variables(lower=0, upper=gstar, name="rdn")

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

    if cross_zonal_cap is not None:
        # zones touching an overloaded line are "congested"; remedial volume
        # outside them is countertrading, capped as a share of the total
        _, ov = overloads(d, ptdf, g_star, fdc_star.values)
        hot = ov.sum(axis=1)[ov.sum(axis=1) > 0].index
        congested = set(d["lines"].loc[hot, ["zone0", "zone1"]]
                        .values.ravel())
        outside = gens.index[~gens.zone.isin(congested)]
        if len(outside) and len(congested):
            share = float(cross_zonal_cap)
            out_sel = (rup.sel(gen=list(outside))
                       + rdn.sel(gen=list(outside))).sum()
            m.add_constraints(
                out_sel - share * (rup + rdn).sum() <= 0,
                name="cross_zonal_cap")

    mc = xr.DataArray(d["mc"].values,
                      coords={"gen": gens.index, "t": t}, dims=["gen", "t"])
    m.add_objective((mc * rup).sum() - (mc * rdn).sum()
                    + beta * (rup + rdn).sum())
    _solve(m, solver_name, solver_options)
    rup_s = rup.solution.to_pandas()
    rdn_s = rdn.solution.to_pandas()
    g_final = g_star + rup_s - rdn_s
    rd_cost = float((d["mc"].values * (rup_s - rdn_s).values).sum())
    return dict(rup=rup_s, rdn=rdn_s, g=g_final, rd_cost=rd_cost,
                volume=float((rup_s + rdn_s).values.sum()))
