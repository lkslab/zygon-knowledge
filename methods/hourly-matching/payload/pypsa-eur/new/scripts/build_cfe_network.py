# SPDX-License-Identifier: MIT
#
# Participating consumer + procurement palette — zygon methods payload
# `hourly-matching` (shared with `annual-matching`). Reads the settled
# prepared sector network, adds ONE clean-procurement consumer the way
# Riepin et al. (2024) do — a flat load at its own bus behind the zone's AC
# bus, a contracted portfolio of NEW (additional) assets sited in the same
# zone, an import link and a capped export link to the grid — and writes the
# variant prepared network for solve_cfe_network. The matching rule itself is
# added at solve time by zygon_cfe_constraints.py, keyed by the variant's
# window; this script only decides WHAT exists.
#
# Layout per consumer <name> (every component name starts `zcfe:<name>:`,
# the selector the constraint module and the collector use):
#   Bus   zcfe:<name>:bus            AC, co-located with the zone bus
#   Load  zcfe:<name>:load           flat p_mw (or a csv profile), carrier electricity
#   Link  zcfe:<name>:import         zone -> consumer, grid_capacity * p_mw, fixed
#   Link  zcfe:<name>:export         consumer -> zone (excess sales, capped at solve time)
#   palette tokens, all p_nom/e_nom 0 and extendable, costs and profiles
#   CLONED from the zone's own components so nothing is invented:
#     onwind | solar | solar-hsat | offwind-ac | offwind-dc | offwind-float
#            -> Generator zcfe:<name>:<carrier> (p_max_pu series of the source,
#               p_nom_max = potential_share * source p_nom_max)
#     battery -> Bus zcfe:<name>:battery + Store + links
#               `zcfe:<name>:battery charger|discharger` (names keep the
#               substring add_battery_constraints couples on)
#     ldes    -> Bus zcfe:<name>:H2 + `H2 Electrolysis` + `H2 Store` + `H2 Fuel Cell`
#     firm    -> Generator clone of zygon_cfe.firm.from_carrier at the zone bus,
#               or explicit params under zygon_cfe.firm
# A variant with window `none` (the no-rule counterfactual) gets the consumer
# and the grid links only: it buys the grid mix, nothing is contracted.
# An empty selection anywhere is a HARD ERROR — a silently unchanged variant
# is the dead-key failure class the zygon harness exists to catch.

import logging

import numpy as np
import pandas as pd
import pypsa

logger = logging.getLogger(__name__)

VRE = ("onwind", "solar", "solar-hsat", "offwind-ac", "offwind-dc", "offwind-float")
GEN_KEEP = ("capital_cost", "marginal_cost", "lifetime", "build_year", "efficiency",
            "location", "unit")
STORE_KEEP = ("capital_cost", "marginal_cost", "standing_loss", "lifetime",
              "build_year", "location")
LINK_KEEP = ("efficiency", "capital_cost", "marginal_cost", "lifetime",
             "build_year", "location")


def prefix_of(name):
    return f"zcfe:{name}:"


def pick(df, mask, what):
    hit = df[mask]
    if hit.empty:
        raise ValueError(f"{what}: no source component to clone from — the "
                         "palette can only contract what the zone already "
                         "models")
    ext = hit[hit.get("p_nom_extendable", hit.get("e_nom_extendable", False))
              .astype(bool)] if ("p_nom_extendable" in hit or "e_nom_extendable" in hit) else hit
    row = (ext if not ext.empty else hit).iloc[0]
    logger.info("%s: cloning '%s'", what, row.name)
    return row


def keep(row, attrs):
    out = {}
    for a in attrs:
        if a in row.index and not (isinstance(row[a], float) and np.isnan(row[a])):
            out[a] = row[a]
    return out


def add_consumer(n, cfg, add_palette):
    c = cfg["consumer"]
    name, zone = str(c["name"]), str(c["bus"])
    pre = prefix_of(name)
    if zone not in n.buses.index:
        raise KeyError(f"consumer bus '{zone}' is not a bus of the network "
                       f"(AC buses: {list(n.buses.index[n.buses.carrier == 'AC'])[:10]})")
    if n.buses.at[zone, "carrier"] != "AC":
        raise ValueError(f"consumer bus '{zone}' carries '{n.buses.at[zone, 'carrier']}', "
                         "expected AC")
    if any(n.buses.index.str.startswith(pre)):
        raise ValueError(f"components prefixed '{pre}' already exist — an add "
                         "that overwrites is a hard error")
    zb = n.buses.loc[zone]
    bus = pre + "bus"
    n.add("Bus", bus, carrier="AC", x=zb.x, y=zb.y, country=zb.country,
          location=zb.get("location", zone), unit=zb.get("unit", "MWh_el"))

    p_mw = float(c["p_mw"])
    profile = c.get("profile", "flat")
    if profile in (None, "flat"):
        p_set = pd.Series(p_mw, index=n.snapshots)
    else:
        prof = pd.read_csv(profile, index_col=0, parse_dates=True).iloc[:, 0]
        p_set = prof.reindex(n.snapshots)
        if p_set.isna().any():
            raise ValueError(f"profile '{profile}' does not cover every snapshot")
    n.add("Load", pre + "load", bus=bus, carrier="electricity", p_set=p_set)

    cap = float(c.get("grid_capacity", 10)) * max(p_mw, float(p_set.max()))
    n.add("Link", pre + "import", bus0=zone, bus1=bus, carrier="zcfe import",
          p_nom=cap, p_nom_extendable=False, p_min_pu=0.0, p_max_pu=1.0,
          efficiency=1.0, capital_cost=0.0, marginal_cost=0.0, location=zone)
    n.add("Link", pre + "export", bus0=bus, bus1=zone, carrier="zcfe export",
          p_nom=cap, p_nom_extendable=False, p_min_pu=0.0, p_max_pu=1.0,
          efficiency=1.0, capital_cost=0.0, marginal_cost=0.0, location=zone)
    for carrier in ("zcfe import", "zcfe export"):
        if carrier not in n.carriers.index:
            n.add("Carrier", carrier)
    added = [bus, pre + "load", pre + "import", pre + "export"]
    if not add_palette:
        return added

    share = float(cfg.get("potential_share", 1.0))
    palette = list(cfg.get("palette") or [])
    if "solar-hsat" in palette and "solar" not in palette:
        raise ValueError("palette: 'solar-hsat' needs 'solar' beside it — "
                         "add_solar_potential_constraints groups both per bus")
    for token in palette:
        if token in VRE:
            src = pick(n.generators, (n.generators.bus == zone)
                       & (n.generators.carrier == token), f"palette {token}")
            gname = pre + token
            n.add("Generator", gname, bus=bus, carrier=token, p_nom=0.0,
                  p_nom_extendable=True,
                  p_nom_max=share * float(src.p_nom_max),
                  p_max_pu=n.generators_t.p_max_pu[src.name],
                  **keep(src, GEN_KEEP))
            added.append(gname)
        elif token == "battery":
            sbus = pre + "battery"
            zbat = n.stores[(n.stores.carrier == "battery")
                            & (n.stores.bus.map(n.buses.location) == zb.get("location", zone))]
            src = pick(n.stores, n.stores.index.isin(zbat.index), "palette battery store")
            n.add("Bus", sbus, carrier="battery", x=zb.x, y=zb.y, country=zb.country,
                  location=zb.get("location", zone), unit="MWh_el")
            n.add("Store", sbus, bus=sbus, carrier="battery", e_nom=0.0,
                  e_nom_extendable=True, e_nom_max=np.inf, e_cyclic=True,
                  **keep(src, STORE_KEEP))
            ch = pick(n.links, (n.links.carrier == "battery charger")
                      & (n.links.bus0 == zone), "palette battery charger")
            dis = pick(n.links, (n.links.carrier == "battery discharger")
                       & (n.links.bus1 == zone), "palette battery discharger")
            n.add("Link", pre + "battery charger", bus0=bus, bus1=sbus,
                  carrier="battery charger", p_nom=0.0, p_nom_extendable=True,
                  **keep(ch, LINK_KEEP))
            n.add("Link", pre + "battery discharger", bus0=sbus, bus1=bus,
                  carrier="battery discharger", p_nom=0.0, p_nom_extendable=True,
                  **keep(dis, LINK_KEEP))
            added += [sbus, pre + "battery charger", pre + "battery discharger"]
        elif token == "ldes":
            hbus = pre + "H2"
            el = pick(n.links, (n.links.carrier == "H2 Electrolysis")
                      & (n.links.bus0 == zone), "palette ldes electrolysis")
            st = pick(n.stores, (n.stores.carrier == "H2 Store")
                      & (n.stores.bus == el.bus1), "palette ldes H2 store")
            fc = pick(n.links, (n.links.carrier == "H2 Fuel Cell")
                      & (n.links.bus1 == zone), "palette ldes fuel cell")
            n.add("Bus", hbus, carrier="H2", x=zb.x, y=zb.y, country=zb.country,
                  location=zb.get("location", zone), unit="MWh_LHV")
            n.add("Link", pre + "H2 Electrolysis", bus0=bus, bus1=hbus,
                  carrier="H2 Electrolysis", p_nom=0.0, p_nom_extendable=True,
                  **keep(el, LINK_KEEP))
            n.add("Store", pre + "H2 Store", bus=hbus, carrier="H2 Store",
                  e_nom=0.0, e_nom_extendable=True, e_nom_max=np.inf,
                  e_cyclic=True, **keep(st, STORE_KEEP))
            n.add("Link", pre + "H2 Fuel Cell", bus0=hbus, bus1=bus,
                  carrier="H2 Fuel Cell", p_nom=0.0, p_nom_extendable=True,
                  **keep(fc, LINK_KEEP))
            added += [hbus, pre + "H2 Electrolysis", pre + "H2 Store", pre + "H2 Fuel Cell"]
        elif token == "firm":
            f = dict(cfg.get("firm") or {})
            if "from_carrier" in f and "capital_cost" not in f:
                src = pick(n.generators, (n.generators.bus == zone)
                           & (n.generators.carrier == f["from_carrier"]),
                           f"palette firm ({f['from_carrier']})")
                params = keep(src, GEN_KEEP)
                params["p_max_pu"] = float(src.get("p_max_pu", 1.0))
                carrier = str(src.carrier)
            else:
                for k in ("carrier", "capital_cost", "marginal_cost"):
                    if k not in f:
                        raise KeyError(f"zygon_cfe.firm needs '{k}' (or from_carrier)")
                carrier = str(f["carrier"])
                params = {"capital_cost": float(f["capital_cost"]),
                          "marginal_cost": float(f["marginal_cost"]),
                          "p_max_pu": float(f.get("p_max_pu", 1.0)),
                          "lifetime": float(f.get("lifetime", 30)),
                          "location": zone}
                if carrier not in n.carriers.index:
                    n.add("Carrier", carrier, co2_emissions=float(f.get("co2_emissions", 0.0)))
            n.add("Generator", pre + "firm", bus=bus, carrier=carrier, p_nom=0.0,
                  p_nom_extendable=True, p_nom_max=np.inf, **params)
            added.append(pre + "firm")
        else:
            raise ValueError(f"palette token '{token}' unknown — want one of "
                             f"{VRE + ('battery', 'ldes', 'firm')}")
    return added


def restore_dtypes(n, before):
    """n.add leaves MODEL-specific static columns (e.g. links.reversed) NaN
    on the new rows, which coerces the column dtype and crashes downstream
    code indexing on it. Neutral-fill and restore the pre-add dtype."""
    for comp, dtypes in before.items():
        df = getattr(n, comp)
        for col, dtype in dtypes.items():
            if col not in df.columns or df[col].dtype == dtype:
                continue
            fill = False if dtype == bool else (0 if np.issubdtype(dtype, np.number) else "")
            df[col] = df[col].fillna(fill).astype(dtype)


if __name__ == "__main__":
    if snakemake.log:  # noqa: F821
        logging.basicConfig(filename=str(snakemake.log[0]),  # noqa: F821
                            level=logging.INFO)

    zcfe = str(snakemake.wildcards.zcfe)  # noqa: F821
    variant = dict(snakemake.params.variant)  # noqa: F821
    cfg = dict(snakemake.params.cfe)  # noqa: F821
    window = str(variant.get("window", "none"))
    if window not in ("none", "year", "month", "hour"):
        raise ValueError(f"variant '{zcfe}': window must be none|year|month|hour, "
                         f"got {window!r}")

    n = pypsa.Network(snakemake.input.network)  # noqa: F821
    before = {c: getattr(n, c).dtypes.copy()
              for c in ("buses", "loads", "generators", "links", "stores")}
    added = add_consumer(n, cfg, add_palette=(window != "none"))
    restore_dtypes(n, before)
    logger.info("variant '%s' (window %s, score %s): added %d component(s): %s",
                zcfe, window, variant.get("score"), len(added), added)
    n.meta = dict(n.meta or {})
    n.meta["zygon_cfe"] = {"variant": zcfe, "window": window,
                           "score": variant.get("score"),
                           "consumer": cfg["consumer"]["name"], "added": added}
    n.export_to_netcdf(snakemake.output[0])  # noqa: F821
