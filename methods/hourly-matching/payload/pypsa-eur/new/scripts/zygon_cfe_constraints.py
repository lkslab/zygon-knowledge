# SPDX-License-Identifier: MIT
#
# The matching rule — zygon methods payload `hourly-matching` (shared with
# `annual-matching`). Loaded by scripts/solve_network.py as the
# custom_extra_functionality of rule solve_cfe_network and called AFTER the
# model's own constraints with (n, snapshots, snakemake); solve_network.py
# looks up the function NAMED LIKE THIS FILE, so the entry point below must
# stay `zygon_cfe_constraints`.
#
# Riepin et al. (2024), for the consumer built by build_cfe_network.py:
#   Eq. 1  annual (window year):   sum_t w_t (A_t [+ S_t])        >=  x sum_t w_t L_t
#   Eq. 2  hourly (window hour):   G_t + S_t + I_t CFE_t - X_t     >=  x L_t   for every t
#   monthly (window month):        Eq. 1 per calendar month (12 rows)
# with A the contracted plants' AVAILABLE generation (p_max_pu x p_nom — the
# volume a PPA contracts, curtailed or sold; basis `available`), G their
# DISPATCHED output (basis `dispatched`; load-shedding slack excluded), S the
# NET contribution of the contracted storage — discharge delivered minus
# charging drawn, so a pass-through or a grid-charged battery earns nothing
# (per-window switch credit_storage), X the excess sold to the grid, I the
# grid import credited at the grid's hourly carbon-free share CFE_t (only
# when grid_cfe.series names a csv — otherwise imports are uncredited and
# the problem stays linear, the one-solve form), x the CFE score / matching
# share, L the consumer's load, w the snapshot weightings (applied on BOTH
# sides — at 3-hourly resolution an unweighted sum understates energy 3x).
# The basis matters: counting DISPATCHED generation under a volumetric rule
# with a binding excess cap makes every imported MWh need a dispatched MWh
# with nowhere to go, and the LP builds a lossy charger/discharger loop as
# the sink (found on the first end-to-end run). Default basis: year and
# month available, hour dispatched (the 24/7 rule is about what is consumed).
# Plus:  sum_t w_t X_t <= excess_share * sum_t w_t L_t      (Riepin's 20% cap)
#        C_t <= G_t  per t when charge_from_portfolio_only  (the stricter
#        "storage charged from contracted supply only" reading; net
#        accounting already denies a grid-charged battery any credit)
# Window `none` adds nothing: the no-rule counterfactual.
# Row counts are logged against the window count — the characteristic silent
# failure is a constraint added for a subset of windows, or none.

import logging

import numpy as np
import pandas as pd
import xarray as xr
from pypsa.descriptors import get_switchable_as_dense as get_as_dense

logger = logging.getLogger(__name__)

GRID_CARRIERS = ("zcfe import", "zcfe export")
SLACK_CARRIERS = ("load",)   # load shedding / load sinks land at every bus, prefixed too


def components(n, name):
    pre = f"zcfe:{name}:"
    bus = pre + "bus"
    if bus not in n.buses.index:
        raise KeyError(f"consumer bus '{bus}' missing — build_cfe_network did "
                       "not run for this variant")
    load = pre + "load"
    g = n.generators[n.generators.index.str.startswith(pre)]
    gens = list(g.index[~g.carrier.isin(SLACK_CARRIERS)])
    links = n.links[n.links.index.str.startswith(pre)]
    imp, exp = pre + "import", pre + "export"
    for x in (load, imp, exp):
        if x not in (n.loads.index if x == load else n.links.index):
            raise KeyError(f"'{x}' missing from the variant network")
    own = links[~links.carrier.isin(GRID_CARRIERS)]
    dischargers = own[own.bus1 == bus]   # deliver into the consumer bus
    chargers = own[own.bus0 == bus]      # draw from the consumer bus
    return {"bus": bus, "load": load, "gens": gens, "imp": imp, "exp": exp,
            "dischargers": dischargers, "chargers": chargers}


def da(series, sns):
    return xr.DataArray(series.reindex(sns).values, coords={"snapshot": sns},
                        dims="snapshot")


def available(m, n, sns, names):
    """Available generation of contracted plants: p_max_pu x p_nom (variable)
    for plants with a capacity-factor series, dispatched output otherwise
    (firm plants — a PPA on those counts delivered energy)."""
    series = [g for g in names if g in n.generators_t.p_max_pu.columns]
    firm = [g for g in names if g not in series]
    expr = None
    if series:
        var = m["Generator-p_nom"]
        dim = [d for d in var.dims][0]
        cf = get_as_dense(n, "Generator", "p_max_pu", sns)[series]
        da_cf = xr.DataArray(cf.values, coords={"snapshot": sns, dim: series},
                             dims=("snapshot", dim))
        expr = (var.sel({dim: series}) * da_cf).sum(dim)
    if firm:
        e = pick(m["Generator-p"], sns, firm)
        expr = e if expr is None else expr + e
    return expr


def pick(var, sns, names):
    """Select components of a linopy variable and sum over them. The
    component dim is `name` in pypsa 1.x and `Generator`/`Link` before; take
    whichever dim is not the snapshot."""
    dim = [d for d in var.dims if d != "snapshot"][0]
    return var.sel({"snapshot": sns, dim: list(names)}).sum(dim)


def pick_scaled(var, sns, names, factor):
    dim = [d for d in var.dims if d != "snapshot"][0]
    f = xr.DataArray(np.asarray(factor, dtype=float), coords={dim: list(names)}, dims=dim)
    return (var.sel({"snapshot": sns, dim: list(names)}) * f).sum(dim)


def zygon_cfe_constraints(n, snapshots, snakemake):
    # the solve rule passes the run's own zygon_cfe (config_provider); the
    # base config is the fallback for a solve rule that does not
    cfg = snakemake.params.get("cfe") or snakemake.config["zygon_cfe"]
    label = str(snakemake.wildcards.zcfe)
    variant = dict(cfg["variants"][label])
    window = str(variant.get("window", "none"))
    name = str(cfg["consumer"]["name"])
    if window == "none":
        logger.info("zygon_cfe: variant '%s' has no matching rule (window none)", label)
        return
    score = float(variant.get("score", 1.0))
    if not 0.0 < score <= 1.0:
        raise ValueError(f"variant '{label}': score must be in (0, 1], got {score}")
    credit = dict(cfg.get("credit_storage") or {})
    credit_storage = bool(credit.get(window, window == "hour"))
    c = components(n, name)
    sns = pd.DatetimeIndex(snapshots)
    w = da(n.snapshot_weightings.generators, sns)

    m = n.model
    if not c["gens"]:
        raise ValueError(f"variant '{label}': the consumer has no contracted "
                         "generators — an empty palette cannot match anything")
    default_basis = {"year": "available", "month": "available", "hour": "dispatched"}
    basis = str((cfg.get("basis") or {}).get(window, default_basis[window]))
    if basis not in ("available", "dispatched"):
        raise ValueError(f"basis for window {window} must be available|dispatched, got {basis!r}")
    if basis == "available":
        supply = available(m, n, sns, c["gens"])
    else:
        supply = pick(m["Generator-p"], sns, c["gens"])
    if credit_storage and not c["dischargers"].empty:
        supply = supply + pick_scaled(m["Link-p"], sns, c["dischargers"].index,
                                      c["dischargers"].efficiency.values)
        if not c["chargers"].empty:
            supply = supply - pick(m["Link-p"], sns, c["chargers"].index)
    export = pick(m["Link-p"], sns, [c["exp"]])
    if basis == "dispatched":
        supply = supply - export
    series = (cfg.get("grid_cfe") or {}).get("series")
    if series:
        cfe = pd.read_csv(series, index_col=0, parse_dates=True).iloc[:, 0]
        if cfe.reindex(sns).isna().any():
            raise ValueError(f"grid_cfe.series '{series}' does not cover every snapshot")
        supply = supply + pick(m["Link-p"], sns, [c["imp"]]) * da(cfe.clip(0, 1), sns)
        logger.info("zygon_cfe: crediting grid imports at the CFE factor from %s "
                    "(mean %.3f) — this is one fixed-point pass", series, float(cfe.mean()))

    load = get_as_dense(n, "Load", "p_set", sns)[c["load"]]
    lhs = supply * w
    rhs = da(score * load, sns) * w

    if window == "hour":
        m.add_constraints(lhs >= rhs, name="zcfe_match_hour")
        rows = len(sns)
    elif window == "month":
        rows = 0
        for month, idx in sns.groupby(sns.month).items():
            m.add_constraints(lhs.sel(snapshot=idx).sum("snapshot")
                              >= float(rhs.sel(snapshot=idx).sum()),
                              name=f"zcfe_match_month_{int(month):02d}")
            rows += 1
    elif window == "year":
        m.add_constraints(lhs.sum("snapshot") >= float(rhs.sum()), name="zcfe_match_year")
        rows = 1
    else:
        raise ValueError(f"variant '{label}': window must be none|year|month|hour, got {window!r}")
    expected = {"hour": len(sns), "month": len(set(sns.month)), "year": 1}[window]
    if rows != expected:
        raise RuntimeError(f"zygon_cfe: added {rows} matching rows, expected {expected}")
    logger.info("zygon_cfe: variant '%s' window %s score %.3f basis %s storage %s -> %d row(s)",
                label, window, score, basis, "credited" if credit_storage else "not credited", rows)

    share = cfg.get("excess_share")
    if share is not None:
        demand = float((da(load, sns) * w).sum())
        m.add_constraints((export * w).sum("snapshot") <= float(share) * demand,
                          name="zcfe_excess_cap")
        logger.info("zygon_cfe: excess sales capped at %.0f%% of %.0f MWh", 100 * float(share), demand)

    if cfg.get("charge_from_portfolio_only", False) and not c["chargers"].empty:
        gen = pick(m["Generator-p"], sns, c["gens"])
        charge = pick(m["Link-p"], sns, c["chargers"].index)
        m.add_constraints(charge - gen <= 0, name="zcfe_charge_from_portfolio")
        logger.info("zygon_cfe: storage charging bounded by contracted generation (%d rows)", len(sns))
