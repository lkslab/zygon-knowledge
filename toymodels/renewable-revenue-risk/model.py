# SPDX-License-Identifier: MIT
"""renewable-revenue-risk: why a wind farm's market revenue gets lower and less
predictable as the system fills up with wind and solar.

The single-node capacity expansion is solved at a sweep of CO2 caps, so the optimiser
builds more wind and solar at every step. Each case's hourly price is then read from the
wind farm's side: how often the price sits at zero, what wind earns per MWh against the
average price (its capture rate), and how much that earning swings from week to week.
The zero-price hours are the ones a CfD or a PPA tops up.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, run  # noqa: E402

SLUG = "renewable-revenue-risk"
TITLE = "Zero-price hours and wind revenue risk"

BASE = run.load_model("capacity-expansion-single-node")
GEN = "onwind"
# CO2 caps as a fraction of the unconstrained emissions; None is no cap
CASES: dict[str, float | None] = {"no cap": None, "50%": 0.5, "20%": 0.2, "5%": 0.05}
ZERO = 1e-3  # EUR/MWh, a price at or below this counts as zero


def build(*, cap_fraction: float | None = None) -> pypsa.Network:
    cap = None if cap_fraction is None else cap_fraction * BASE.reference_emissions()
    return BASE.build(co2_cap_t=cap)


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def sweep(cases: dict[str, float | None] | None = None) -> dict[str, pypsa.Network]:
    """One solved network per CO2 cap, keyed by the cap's label."""
    return {label: solve(build(cap_fraction=frac)) for label, frac in (cases or CASES).items()}


def vre_share_pct(n: pypsa.Network) -> float:
    """Wind and solar as a share of all generation (curtailed energy not counted)."""
    w = n.snapshot_weightings.generators
    supply = n.generators_t.p.mul(w, axis=0).sum()
    return float(100 * (supply["onwind"] + supply["solar"]) / supply.sum())


def label(n: pypsa.Network) -> str:
    """A case named by what it is from the farm's side: its wind and solar share."""
    return f"{vre_share_pct(n):.0f}% wind and solar"


def weekly_wind_value(n: pypsa.Network) -> pd.Series:
    """What wind earned per MWh in each week of the year (market revenue / output)."""
    w = n.snapshot_weightings.generators
    price = n.buses_t.marginal_price["electricity"]
    energy = n.generators_t.p[GEN] * w
    week = n.snapshots.isocalendar().week.clip(upper=52).to_numpy()
    revenue = (price * energy).groupby(week).sum()
    return revenue / energy.groupby(week).sum()


def case_numbers(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    price = n.buses_t.marginal_price["electricity"]
    energy = n.generators_t.p[GEN] * w
    mean_price = float((price * w).sum() / w.sum())
    market_value = float((price * energy).sum() / energy.sum())
    weekly = weekly_wind_value(n)
    return {
        "co2_cap_fraction": None,
        "vre_share_pct": vre_share_pct(n),
        "wind_capacity_mw": float(n.generators.p_nom_opt[GEN]),
        "share_hours_zero_price_pct": float(100 * w[price <= ZERO].sum() / w.sum()),
        "share_wind_energy_at_zero_price_pct": float(100 * energy[price <= ZERO].sum() / energy.sum()),
        "mean_price_eur_mwh": mean_price,
        "wind_market_value_eur_mwh": market_value,
        "wind_capture_rate": market_value / mean_price,
        "weekly_wind_value_min_eur_mwh": float(weekly.min()),
        "weekly_wind_value_max_eur_mwh": float(weekly.max()),
        "weekly_wind_value_cv": float(weekly.std() / weekly.mean()),
    }


def numbers(networks: dict[str, pypsa.Network], cases: dict[str, float | None] | None = None) -> dict:
    cases = cases or CASES
    out = {}
    for cap, n in networks.items():
        out[cap] = {**case_numbers(n), "co2_cap_fraction": cases.get(cap)}
    return out


def figures(networks: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    labels = {cap: label(n) for cap, n in networks.items()}
    nums = {cap: case_numbers(n) for cap, n in networks.items()}
    trend = pd.DataFrame(
        {
            "hours at zero price": [nums[c]["share_hours_zero_price_pct"] for c in networks],
            "wind capture rate": [100 * nums[c]["wind_capture_rate"] for c in networks],
        },
        index=pd.Index([round(nums[c]["vre_share_pct"], 1) for c in networks], name="x"),
    ).round(2)
    option, ds = charts.xy_lines(trend, "Wind and solar share of generation (%)", "%", symbols=True,
                                 x_extra={"min": 40, "max": 100})
    trend_fig = bundle.Figure(option, ds, title="More wind and solar: more zero-price hours, less per MWh for wind",
                              caption="Each point is one optimal system under a tighter CO2 cap. The share of hours "
                              "at zero price rises, and what wind earns per MWh falls against the average price "
                              "(capture rate), because wind produces most exactly when the price is zero.")
    # the least and the most renewable case only: two lines read as a contrast, four as noise
    ends = list(dict.fromkeys([min(networks, key=lambda c: nums[c]["vre_share_pct"]),
                               max(networks, key=lambda c: nums[c]["vre_share_pct"])]))
    weekly = pd.DataFrame({labels[c]: weekly_wind_value(networks[c]) for c in ends}).round(2)
    weekly.index.name = "x"
    option, ds = charts.xy_lines(weekly, "Week of the year", "EUR/MWh", x_extra={"min": 1, "max": 52})
    weekly_fig = bundle.Figure(option, ds, title="What wind earns per MWh, week by week",
                               caption="Market revenue over output in each week, for the least and the most renewable "
                               "case. With less wind and solar the week-to-week earning is steadier; with a lot it "
                               "swings between zero in windy weeks and very high values in still ones. A CfD or a PPA replaces this line with a flat one.")
    curves = {labels[c]: n.buses_t.marginal_price["electricity"] for c, n in networks.items()}
    option, ds = charts.duration_curves(curves, "EUR/MWh")
    option["yAxis"]["max"] = 500
    pdc = bundle.Figure(option, ds, title="Price duration curves by wind and solar share",
                        caption="The year's prices sorted from high to low (axis clipped at 500 EUR/MWh; scarcity "
                        "hours go higher). The block at zero widens as wind and solar grow, and the remaining "
                        "revenue concentrates in fewer, higher-priced hours.")
    return {"zero_price_and_capture_rate": trend_fig, "weekly_wind_revenue": weekly_fig, "price_duration_by_case": pdc}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    networks = sweep()
    nums = numbers(networks)
    figs = figures(networks)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
