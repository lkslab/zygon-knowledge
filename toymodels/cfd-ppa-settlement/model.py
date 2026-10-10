# SPDX-License-Identifier: MIT
"""cfd-ppa-settlement: what a wind farm earns under different support and contract
schemes, settled after the market has cleared.

The 20 % cap year of the cost-recovery model is solved once; nothing about the
dispatch changes. The wind farm's hourly output and the hourly price are then settled
under an energy-only market, a two-sided contract for difference, a fixed premium, a
cap-and-floor, a pay-as-produced PPA and a baseload PPA, plus a CfD variant that pays
no top-up in zero-price hours. Same electrons, very different cheques.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, names, run  # noqa: E402

SLUG = "cfd-ppa-settlement"
TITLE = "Subsidies, CfDs and PPAs settled on one wind farm"

BASE = run.load_model("price-duration-and-cost-recovery")
GEN = "onwind"
STRIKE = 70.0  # EUR/MWh, two-sided CfD
PREMIUM = 20.0  # EUR/MWh on top of the market price
FLOOR, CAP = 30.0, 120.0  # cap-and-floor on the market price
PPA_PRICE = 65.0  # pay-as-produced PPA
BASELOAD_PRICE = 65.0  # baseload PPA: flat volume equal to the mean output
# ten days with long zero-price stretches and a few scarcity spikes, top-up and payback
# of similar size: the window the two intuition figures draw
WINDOW = ("2025-03-26", "2025-04-05")


def build() -> pypsa.Network:
    return BASE.build()


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def series(n: pypsa.Network) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Hourly price, wind output and snapshot weight."""
    return n.buses_t.marginal_price["electricity"], n.generators_t.p[names.gen(GEN)], n.snapshot_weightings.generators


def settle(n: pypsa.Network) -> pd.DataFrame:
    """Revenue per snapshot (EUR, weighted) under every scheme."""
    price, p, w = series(n)
    energy = p * w
    market = price * energy
    flat = float(energy.sum() / w.sum())  # MW, the baseload PPA volume
    schemes = {
        "energy-only market": market,
        "two-sided CfD": STRIKE * energy,
        "CfD, no top-up at zero price": market.where(price <= 0, STRIKE * energy),
        "fixed premium": (price + PREMIUM) * energy,
        "cap-and-floor": price.clip(FLOOR, CAP) * energy,
        "pay-as-produced PPA": PPA_PRICE * energy,
        "baseload PPA": market + (BASELOAD_PRICE - price) * flat * w,
    }
    return pd.DataFrame(schemes)


def numbers(n: pypsa.Network) -> dict:
    price, p, w = series(n)
    rev = settle(n)
    energy = float((p * w).sum())
    mean_price = float((price * w).sum() / w.sum())
    market_value = float(rev["energy-only market"].sum() / energy)
    cr = finance.cost_recovery(n)
    cost = float(cr.loc[GEN, "cost"])
    return {
        "wind_energy_gwh": energy / 1e3,
        "mean_price_eur_mwh": mean_price,
        "market_value_eur_mwh": market_value,
        "capture_rate": market_value / mean_price,
        "revenue_neutral_strike_eur_mwh": market_value,
        "lcoe_eur_mwh": cost / energy,
        "revenue_meur_a": {k: float(v.sum() / 1e6) for k, v in rev.items()},
        "support_cost_meur_a": {k: float((v - rev["energy-only market"]).sum() / 1e6) for k, v in rev.items()},
        "revenue_per_mwh_eur": {k: float(v.sum() / energy) for k, v in rev.items()},
        "share_hours_zero_price_pct": float(100 * w[price <= 1e-3].sum() / w.sum()),
        "share_wind_energy_at_zero_price_pct": float(100 * (p * w)[price <= 1e-3].sum() / energy),
        "strike_eur_mwh": STRIKE,
        "premium_eur_mwh": PREMIUM,
        "floor_cap_eur_mwh": [FLOOR, CAP],
        "ppa_price_eur_mwh": PPA_PRICE,
    }


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    price, p, w = series(n)
    rev = settle(n)
    labels = list(rev.columns)
    option, ds = charts.bars(labels, {"revenue": (rev.sum() / 1e6).round(3).tolist()}, "MEUR/a", horizontal=True, category_name="scheme")
    annual = bundle.Figure(option, ds, title="Annual wind revenue by scheme",
                           caption="Same output, same prices. The CfD and the pay-as-produced PPA remove price risk; "
                           "the premium and the floor add to it; the baseload PPA carries shape risk because the farm "
                           "must buy back the flat volume in still hours.")
    monthly = rev[["energy-only market", "two-sided CfD", "fixed premium"]].groupby(rev.index.month).sum() / 1e6
    months = [pd.Timestamp(2025, m, 1).strftime("%b") for m in monthly.index]
    option, ds = charts.bars(months, {c: monthly[c].round(3).tolist() for c in monthly.columns}, "MEUR", horizontal=False, category_name="month")
    month_fig = bundle.Figure(option, ds, title="Monthly revenue: market, CfD, premium",
                              caption="The market revenue follows the wind and the price; the CfD follows the wind only, "
                              "so windy months with low prices are where the top-up is largest.")
    window = n.snapshots[(n.snapshots >= WINDOW[0]) & (n.snapshots < WINDOW[1])]
    df = pd.DataFrame({"price": price.loc[window], "onwind": p.loc[window]})
    option, ds = charts.fill_between(df, charts.Band(
        "price", STRIKE, "strike", below="top-up to the farm", above="farm pays back", unit="EUR/MWh"))
    cfd_fig = bundle.Figure(option, ds, title="What a CfD does: the price against the strike",
                            caption="Ten days of the year's price. Below the strike the farm is topped up to it, "
                            "above it the farm pays the excess back: per MWh produced it earns the strike either way.")
    flat = float((p * w).sum() / w.sum())
    option, ds = charts.fill_between(df, [
        charts.Band("price", PPA_PRICE, "PPA price", below="buyer tops up", above="farm hands back", unit="EUR/MWh"),
        charts.Band("onwind", flat, "baseload volume", below="shortfall bought at spot", above="surplus sold at spot",
                    unit="MW", below_color=charts.BAND_ABOVE, above_color=charts.BAND_BELOW),
    ])
    ppa_fig = bundle.Figure(option, ds, title="What a PPA does: a fixed price, and whose volume",
                            caption="Top: a pay-as-produced PPA settles like a CfD, with a company in place of the "
                            "state. Bottom: a baseload PPA promises a flat volume; in still hours the farm must buy the "
                            "shortfall at spot, and still hours are the expensive ones.")
    return {"cfd_intuition": cfd_fig, "ppa_intuition": ppa_fig, "revenue_by_scheme": annual, "monthly_revenue": month_fig}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
