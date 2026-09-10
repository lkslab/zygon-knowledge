# SPDX-License-Identifier: MIT
#
# Per-asset storage economics — zygon methods payload `storage-economics`.
# For every storage asset of the configured carriers in every listed solved
# network, the economic performance metrics an investor or planner reads:
#
#   asset boundary (decided per Store from the network, never by name):
#     external — a Store whose bus carries links of carrier
#                "<store carrier> charger" / "<store carrier> discharger"
#                (battery, home battery, water tanks): the asset is store +
#                links, valued at the links' OUTER buses (what the asset
#                buys and sells on the grid side)
#     store    — any other Store (H2 Store, gas ...): valued at its own bus
#                price, the store alone (its converters serve other demands)
#     unit     — a StorageUnit (PHS, hydro): valued at its bus
#
#   arbitrage_revenue [EUR/a]  sum_t w_t lambda_t (delivered_t - drawn_t)
#   annualised_cost   [EUR/a]  sum capital_cost * nom_opt over the asset's
#                              components (eur capital_cost is annualised and
#                              includes FOM) + marginal_cost * throughput
#   cost_recovery     [-]      arbitrage_revenue / annualised_cost — the LP
#                              zero-profit identity puts a freely built asset
#                              at ~1; existing (sunk) assets carry no capex
#   discharge_energy  [MWh/a]  weighted energy delivered
#   full_cycles       [1/a]    discharge_energy / e_nom_opt
#   capture_price     [EUR/MWh] revenue of delivery / discharge_energy
#   charge_price      [EUR/MWh] cost of drawing / charge_energy
#   spread            [EUR/MWh] capture_price - charge_price
#   duration_h        [h]      e_nom_opt / discharger p_nom_opt, or max_hours
#   utilisation       [-]      discharge_energy / (discharger p_nom_opt * 8760)
#   msv_mean, msv_max [EUR/MWh] weighted mean / max of the energy-balance dual
#                              (marginal storage value), NaN when the solve
#                              did not assign it (solving.options.assign_all_duals)
#
# Weighted with snapshot_weightings.objective. An asset of a listed carrier
# that yields no row, or a hook that raises, aborts the rule loudly.

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

logger = logging.getLogger(__name__)

QUANTITIES = ("arbitrage_revenue", "annualised_cost", "cost_recovery",
              "discharge_energy", "full_cycles", "capture_price", "charge_price",
              "spread", "duration_h", "utilisation", "msv_mean", "msv_max")


def weighted(series, w):
    return float((series * w).sum())


def price_of(n, bus):
    if bus not in n.buses_t.marginal_price.columns:
        raise KeyError(f"no marginal price for bus '{bus}' — was the network solved?")
    return n.buses_t.marginal_price[bus]


def msv(series, w):
    if series is None:
        return float("nan"), float("nan")
    s = series.astype(float)
    if s.isna().all():
        return float("nan"), float("nan")
    return float((s * w).sum() / w.sum()), float(s.max())


def finish(rev_out, cost_in, e_out, e_in, capex, opex, e_nom, p_dis, hours, mu, w):
    rev = rev_out - cost_in
    cost = capex + opex
    m_mean, m_max = msv(mu, w)
    return {
        "arbitrage_revenue": rev,
        "annualised_cost": cost,
        "cost_recovery": rev / cost if cost > 0 else float("nan"),
        "discharge_energy": e_out,
        "full_cycles": e_out / e_nom if e_nom > 0 else float("nan"),
        "capture_price": rev_out / e_out if e_out > 0 else float("nan"),
        "charge_price": cost_in / e_in if e_in > 0 else float("nan"),
        "spread": (rev_out / e_out - cost_in / e_in) if (e_out > 0 and e_in > 0) else float("nan"),
        "duration_h": hours,
        "utilisation": e_out / (p_dis * 8760.0) if p_dis > 0 else float("nan"),
        "msv_mean": m_mean,
        "msv_max": m_max,
    }


def store_asset(n, name, w):
    s = n.stores.loc[name]
    links = n.links[(n.links.bus0 == s.bus) | (n.links.bus1 == s.bus)]
    ch = links[links.carrier == f"{s.carrier} charger"]
    dis = links[links.carrier == f"{s.carrier} discharger"]
    mu = n.stores_t.mu_energy_balance.get(name) if "mu_energy_balance" in n.stores_t else None
    if not ch.empty and not dis.empty and len(links) == len(ch) + len(dis):
        # external boundary: store + its converters, valued on the grid side
        e_out = e_in = rev_out = cost_in = 0.0
        for _, l in dis.iterrows():          # bus0 = store bus -> bus1 outer
            delivered = (-n.links_t.p1[l.name]).clip(lower=0)
            e_out += weighted(delivered, w)
            rev_out += weighted(delivered * price_of(n, l.bus1), w)
        for _, l in ch.iterrows():           # bus0 outer -> bus1 = store bus
            drawn = n.links_t.p0[l.name].clip(lower=0)
            e_in += weighted(drawn, w)
            cost_in += weighted(drawn * price_of(n, l.bus0), w)
        capex = float(s.capital_cost * s.e_nom_opt + (ch.capital_cost * ch.p_nom_opt).sum()
                      + (dis.capital_cost * dis.p_nom_opt).sum())
        opex = float(s.marginal_cost * weighted(n.stores_t.p[name].abs(), w)
                     + sum(l.marginal_cost * weighted(n.links_t.p0[l.name].clip(lower=0), w)
                           for _, l in pd.concat([ch, dis]).iterrows()))
        p_dis = float(dis.p_nom_opt.sum())
        hours = float(s.e_nom_opt / p_dis) if p_dis > 0 else float("nan")
        boundary, bus = "external", dis.bus1.iloc[0]
    else:
        # store boundary: valued at its own bus
        p = n.stores_t.p[name]
        lam = price_of(n, s.bus)
        e_out, e_in = weighted(p.clip(lower=0), w), weighted((-p).clip(lower=0), w)
        rev_out, cost_in = weighted(p.clip(lower=0) * lam, w), weighted((-p).clip(lower=0) * lam, w)
        capex = float(s.capital_cost * s.e_nom_opt)
        opex = float(s.marginal_cost * weighted(p.abs(), w))
        p_dis = float(p.clip(lower=0).max())
        hours = float(s.e_nom_opt / p_dis) if p_dis > 0 else float("nan")
        boundary, bus = "store", s.bus
    row = finish(rev_out, cost_in, e_out, e_in, capex, opex, float(s.e_nom_opt),
                 p_dis, hours, mu, w)
    return boundary, bus, row


def unit_asset(n, name, w):
    u = n.storage_units.loc[name]
    p = n.storage_units_t.p[name]
    lam = price_of(n, u.bus)
    e_out, e_in = weighted(p.clip(lower=0), w), weighted((-p).clip(lower=0), w)
    rev_out, cost_in = weighted(p.clip(lower=0) * lam, w), weighted((-p).clip(lower=0) * lam, w)
    capex = float(u.capital_cost * u.p_nom_opt)
    opex = float(u.marginal_cost * weighted(p.abs(), w))
    e_nom = float(u.p_nom_opt * u.max_hours)
    mu = (n.storage_units_t.mu_energy_balance.get(name)
          if "mu_energy_balance" in n.storage_units_t else None)
    row = finish(rev_out, cost_in, e_out, e_in, capex, opex, e_nom,
                 float(u.p_nom_opt), float(u.max_hours), mu, w)
    return "unit", u.bus, row


def collect(n, carriers, label):
    w = n.snapshot_weightings.objective
    rows = []
    stores = n.stores[n.stores.carrier.isin(carriers)]
    units = n.storage_units[n.storage_units.carrier.isin(carriers)]
    if stores.empty and units.empty:
        raise ValueError(f"network '{label}': no Store or StorageUnit of carriers "
                         f"{carriers} (stores carry {sorted(n.stores.carrier.unique())})")
    for name in stores.index:
        boundary, bus, row = store_asset(n, name, w)
        rows.append((name, n.stores.at[name, "carrier"], bus, boundary, row))
    for name in units.index:
        boundary, bus, row = unit_asset(n, name, w)
        rows.append((name, n.storage_units.at[name, "carrier"], bus, boundary, row))
    logger.info("network '%s': %d storage asset(s) valued", label, len(rows))
    return rows


if __name__ == "__main__":
    if snakemake.log:  # noqa: F821
        logging.basicConfig(filename=str(snakemake.log[0]),  # noqa: F821
                            level=logging.INFO)

    labels = [str(x) for x in snakemake.params.labels]  # noqa: F821
    carriers = [str(x) for x in snakemake.params.carriers]  # noqa: F821
    quantities = [str(x) for x in snakemake.params.quantities]  # noqa: F821
    networks = [str(p) for p in snakemake.input.networks]  # noqa: F821
    csvs = [str(p) for p in snakemake.output.csvs]  # noqa: F821

    if len(labels) != len(networks):
        raise ValueError(f"zygon_storage_economics: {len(labels)} labels for "
                         f"{len(networks)} networks — must match 1:1")
    if len(set(labels)) != len(labels):
        raise ValueError(f"zygon_storage_economics: labels not unique: {labels}")
    unknown = [q for q in quantities if q not in QUANTITIES]
    if unknown:
        raise ValueError(f"zygon_storage_economics: unknown quantities {unknown} "
                         f"(built-in: {list(QUANTITIES)})")

    frames = {q: [] for q in quantities}
    boundaries = {}
    for label, path in zip(labels, networks):
        n = pypsa.Network(path)
        for asset, carrier, bus, boundary, row in collect(n, carriers, label):
            boundaries[f"{label}:{asset}"] = boundary
            for q in quantities:
                frames[q].append((label, asset, carrier, bus, row[q]))

    # expand() preserves quantity order, so csvs[i] belongs to quantities[i]
    for q, csv_path in zip(quantities, csvs):
        pd.DataFrame(frames[q], columns=["network", "asset", "carrier", "bus", "value"]
                     ).to_csv(csv_path, index=False)

    manifest = {"labels": labels, "networks": networks, "carriers": carriers,
                "quantities": quantities, "boundaries": boundaries,
                "csvs": [str(Path(p)) for p in csvs]}
    Path(snakemake.output.manifest).write_text(  # noqa: F821
        json.dumps(manifest, indent=2) + "\n")
