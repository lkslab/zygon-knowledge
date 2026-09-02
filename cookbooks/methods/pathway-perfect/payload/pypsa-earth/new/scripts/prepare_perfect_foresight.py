# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Concatenate the per-horizon sector-coupled prenetworks into one
multi-investment-period network for perfect-foresight optimisation.

Port of pypsa-eur's prepare_perfect_foresight.py concat machinery, reduced
to pypsa-earth's power-cohorts-only scope: MultiIndex snapshots per horizon,
investment_periods, years/objective weightings (social discount rate,
default 0.02). The eur-only blocks (set_all_phase_outs,
hvdc_transport_model, heating/H2 adjustments) are deliberately not ported.

Beyond the eur machinery, one earth-specific repair:
split_period_variant_exogenous. Earth's exogenously sized sector
components (BEV charger, EV battery storage, ...) carry NO period suffix
upstream, so on concat the first period's sizing silently wins the name
collision — any share/demand path then leaves later periods' transport
demand unservable (zygon issues #14/#15). Components whose fixed sizing
differs from the instance already imported are split into per-period
instances windowed via build_year/lifetime, which pypsa's multi-horizon
activity mask (build_year <= period < build_year + lifetime) then
activates one-per-period.
"""
import logging

import numpy as np
import pandas as pd
import pypsa
from _helpers import configure_logging, create_logger

logger = create_logger(__name__)

NOMINAL_ATTRS = {
    "Generator": ["p_nom", "p_nom_min", "p_nom_max"],
    "Link": ["p_nom", "p_nom_min", "p_nom_max"],
    "Store": ["e_nom", "e_nom_min", "e_nom_max"],
    "StorageUnit": ["p_nom", "p_nom_min", "p_nom_max"],
}


def get_social_discount(t, r=0.02):
    """Social discount factor for a single year t."""
    return 1 / (1 + r) ** t


def get_investment_weighting(time_weighting, r=0.02):
    """Objective weighting per investment period: sum of the discounted
    year weights inside each period's window."""
    end = time_weighting.cumsum()
    start = time_weighting.cumsum().shift().fillna(0)
    return pd.concat([start, end], axis=1).apply(
        lambda x: sum(
            get_social_discount(t, r) for t in range(int(x.iloc[0]), int(x.iloc[1]))
        ),
        axis=1,
    )


def get_missing(df, n, list_name):
    """Rows of df not yet present in the target network's component table."""
    df_final = getattr(n, list_name)
    missing_i = df.index.difference(df_final.index)
    return df.loc[missing_i]


def add_build_year_to_new_assets(n, baseyear):
    """Tag new (finite-lifetime, unset build_year) assets with the
    investment year and suffix their names, so build_year/lifetime activity
    windows apply per period inside the joint LP."""
    for c in n.iterate_components(["Link", "Generator", "Store", "StorageUnit"]):
        assets = c.df.index[(c.df.lifetime != np.inf) & (c.df.build_year == 0)]
        c.df.loc[assets, "build_year"] = baseyear

        rename = pd.Series(c.df.index, c.df.index)
        rename[assets] += "-" + str(baseyear)
        c.df.rename(index=rename, inplace=True)

        for attr in c.pnl.keys():
            df = c.pnl[attr]
            if df.empty:
                continue
            df.rename(columns=rename, inplace=True)


def latest_instance(df, name, earlier_years):
    """The most recent per-period instance of `name` already imported:
    the highest '-<year>' suffixed copy, else the unsuffixed original."""
    for y in sorted(earlier_years, reverse=True):
        cand = f"{name}-{y}"
        if cand in df.index:
            return cand
    return name if name in df.index else None


def split_period_variant_exogenous(n, network, year, earlier_years):
    """Rename this period's instance of every exogenously sized component
    whose fixed sizing differs from the latest instance already in n, and
    window that earlier instance to end this year. Renaming happens on the
    INCOMING network (static index + time-series columns), before import,
    so profiles follow their component."""
    for c in network.iterate_components(list(NOMINAL_ATTRS)):
        df_prev = getattr(n, c.list_name)
        if df_prev.empty:
            continue
        ext_attr = next(a for a in ("p_nom_extendable", "e_nom_extendable")
                        if a in c.df)
        attrs = [a for a in NOMINAL_ATTRS[c.name] if a in c.df]
        rename = {}
        for name in c.df.index[~c.df[ext_attr]]:
            prev = latest_instance(df_prev, name, earlier_years)
            if prev is None:
                continue
            differs = any(
                not np.isclose(c.df.at[name, a], df_prev.at[prev, a],
                               rtol=1e-6, atol=1e-6, equal_nan=True)
                for a in attrs
            )
            if not differs:
                continue
            rename[name] = f"{name}-{year}"
            # close the earlier instance's activity window at this year
            if not np.isfinite(df_prev.at[prev, "lifetime"]):
                df_prev.at[prev, "lifetime"] = (
                    year - df_prev.at[prev, "build_year"]
                )
        if not rename:
            continue
        logger.info(
            "%s: %d period-variant exogenous component(s) split for %s",
            c.name, len(rename), year,
        )
        c.df.rename(index=rename, inplace=True)
        c.df.loc[list(rename.values()), "build_year"] = year
        for attr in c.pnl.keys():
            df = c.pnl[attr]
            if not df.empty:
                df.rename(columns=rename, inplace=True)


def add_year_to_constraints(n, baseyear):
    """Tag global constraints with the investment period and make their
    index unique across periods."""
    for component in n.iterate_components(["GlobalConstraint"]):
        component.df["investment_period"] = baseyear
        component.df.rename(index=lambda x: x + "-" + str(baseyear), inplace=True)


def concat_networks(network_paths, years, social_discountrate):
    """Concatenate the given per-horizon networks into one network with
    multi-indexed (period, timestep) snapshots and investment periods."""
    n = pypsa.Network()

    for i, network_path in enumerate(network_paths):
        year = years[i]
        network = pypsa.Network(network_path)
        add_build_year_to_new_assets(network, year)
        if i > 0:
            split_period_variant_exogenous(n, network, year, years[:i])

        # static components: add only what the concatenated network misses
        for component in network.iterate_components(
            [
                "Bus",
                "Carrier",
                "Generator",
                "Link",
                "Store",
                "Load",
                "Line",
                "StorageUnit",
            ]
        ):
            missing = get_missing(component.df.copy(), n, component.list_name)
            n.import_components_from_dataframe(missing, component.name)

        # time-varying data on the growing MultiIndex
        network_sns = pd.MultiIndex.from_product([[year], network.snapshots])
        snapshots = n.snapshots.drop("now", errors="ignore").union(network_sns)
        n.set_snapshots(snapshots)

        for component in network.iterate_components():
            pnl = getattr(n, component.list_name + "_t")
            for k in list(component.pnl.keys()):
                pnl_year = component.pnl[k].copy().reindex(snapshots, level=1)
                if pnl_year.empty and not (
                    component.name == "Load" and k == "p_set"
                ):
                    continue
                if k not in pnl:
                    pnl[k] = pd.DataFrame(index=snapshots)
                if component.name == "Load":
                    static_load = network.loads.loc[network.loads.p_set != 0]
                    static_load_t = pd.DataFrame(
                        np.outer(
                            np.ones(len(network_sns)), static_load.p_set.values
                        ),
                        index=network_sns,
                        columns=static_load.index,
                    )
                    pnl_year = pd.concat(
                        [pnl_year.reindex(network_sns), static_load_t], axis=1
                    )
                    columns = (pnl[k].columns.union(pnl_year.columns)).unique()
                    pnl[k] = pnl[k].reindex(columns=columns)
                    pnl[k].loc[pnl_year.index, pnl_year.columns] = pnl_year
                else:
                    # carry earlier periods' series forward for pre-existing
                    # components, then append the new components' series
                    if i > 0 and not pnl[k].empty:
                        pnl[k].loc[(year,)] = pnl[k].loc[(years[i - 1],)].values
                    cols = pnl_year.columns.difference(pnl[k].columns)
                    pnl[k] = pd.concat([pnl[k], pnl_year[cols]], axis=1)
                    # this period's own values override the carry-forward
                    # for columns present in both (per-period profiles of
                    # split exogenous instances arrive suffixed, so this
                    # only refreshes genuinely shared components)
                    shared = pnl_year.columns.intersection(pnl[k].columns)
                    if i > 0 and len(shared):
                        pnl[k].loc[(year,), shared] = (
                            pnl_year.reindex(network_sns)[shared].values
                        )

        n.snapshot_weightings.loc[year, :] = network.snapshot_weightings.values

        add_year_to_constraints(network, year)
        for component in network.iterate_components(["GlobalConstraint"]):
            n.import_components_from_dataframe(component.df, component.name)

    # investment periods + years/objective weightings
    n.investment_periods = n.snapshots.levels[0]
    time_w = n.investment_periods.to_series().diff().shift(-1).ffill()
    n.investment_period_weightings["years"] = time_w
    n.investment_period_weightings["objective"] = get_investment_weighting(
        n.investment_period_weightings["years"], social_discountrate
    )

    # all former static loads are now time-dependent
    n.loads["p_set"] = 0
    n.loads_t.p_set.fillna(0, inplace=True)

    return n


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake(
            "prepare_perfect_foresight",
            simpl="",
            clusters="4",
            ll="c1",
            opts="Co2L-4H",
            discountrate="0.071",
            demand="AB",
            sopts="144H",
            h2export="120",
            configfile="config.tutorial.yaml",
        )

    configure_logging(snakemake)

    years = [int(y) for y in snakemake.params.planning_horizons]
    social_discountrate = float(snakemake.params.social_discountrate)
    network_paths = list(snakemake.input.networks)

    logger.info(
        "Concatenating %d networks over investment periods %s (r=%s)",
        len(network_paths),
        years,
        social_discountrate,
    )
    n = concat_networks(network_paths, years, social_discountrate)

    n.meta = dict(snakemake.config, **dict(wildcards=dict(snakemake.wildcards)))
    n.export_to_netcdf(snakemake.output[0])
