# SPDX-License-Identifier: MIT
"""Annuities, capital costs and cost-recovery bookkeeping shared by the toy models."""

from __future__ import annotations

import pandas as pd
import pypsa

DISCOUNT_RATE = 0.07


def annuity(rate: float, life_years: int) -> float:
    """Annuity factor: the share of an overnight cost paid every year over `life_years`."""
    if rate == 0:
        return 1 / life_years
    return rate / (1 - (1 + rate) ** (-life_years))


def capital_cost(
    overnight_eur_per_kw: float,
    life_years: int,
    *,
    rate: float = DISCOUNT_RATE,
    fom_pct: float = 0.0,
) -> float:
    """Annualised capital cost in EUR per MW per year (what `capital_cost` in PyPSA wants).

    `fom_pct` adds fixed O&M as a percentage of the overnight cost per year.
    """
    return overnight_eur_per_kw * 1e3 * (annuity(rate, life_years) + fom_pct / 100)


def lcoe(annual_cost_eur: float, annual_output_mwh: float) -> float:
    """Levelised cost, EUR/MWh; NaN when nothing was produced."""
    return annual_cost_eur / annual_output_mwh if annual_output_mwh > 0 else float("nan")


def by_carrier(frame: pd.Series) -> pd.Series:
    """Collapse a statistics result indexed (component, carrier) onto carrier."""
    if isinstance(frame.index, pd.MultiIndex) and "carrier" in frame.index.names:
        return frame.groupby(level="carrier").sum()
    return frame


def cost_recovery(n: pypsa.Network) -> pd.DataFrame:
    """Revenue, annualised cost and their ratio per carrier, from `n.statistics`.

    Revenue follows `n.statistics.revenue()` (net of what a component pays for its
    inputs); cost is `capex()` (already annualised through `capital_cost`) plus
    `opex()`. For an extendable technology built at the optimum of an LP the
    ratio is one: that is the zero-profit condition of a competitive market.
    """
    revenue = by_carrier(n.statistics.revenue())
    capex = by_carrier(n.statistics.capex())
    opex = by_carrier(n.statistics.opex())
    out = pd.DataFrame({"revenue": revenue, "capex": capex, "opex": opex}).fillna(0.0)
    out["cost"] = out["capex"] + out["opex"]
    out["ratio"] = out["revenue"] / out["cost"].where(out["cost"] > 0)
    return out
