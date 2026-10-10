# SPDX-License-Identifier: MIT
"""price-duration-and-cost-recovery: do the technologies an optimiser builds earn
their money back at the prices the same optimiser produces?

Reuses the single-node capacity expansion at a 20 % CO2 cap. In a linear programme
every technology built at the optimum recovers exactly its annualised capital plus
operating cost from the market price: the zero-profit condition. The price duration
curve shows where that revenue comes from, a few scarcity hours and long stretches at
the marginal cost of gas or at zero.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, names, run  # noqa: E402
from _lib import carrier_style as cs  # noqa: E402

SLUG = "price-duration-and-cost-recovery"
TITLE = "Price duration and cost recovery"
CAP_FRACTION = 0.2
BASE = run.load_model("capacity-expansion-single-node")
TECHS = ["onwind", "solar", "CCGT", "battery", "H2 Electrolysis", "H2 Fuel Cell", "H2 Store"]


def build(*, cap_fraction: float = CAP_FRACTION) -> pypsa.Network:
    return BASE.build(co2_cap_t=cap_fraction * BASE.reference_emissions())


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def co2_price(n: pypsa.Network) -> float:
    return float(-n.global_constraints.mu["co2_limit"])


def gas_price_level(n: pypsa.Network) -> float:
    """The price gas sets when it is marginal: fuel plus the CO2 shadow price on its emissions."""
    return BASE.TECH["CCGT"]["marginal_cost"] + co2_price(n) * BASE.CO2_CCGT


def costs_with_carbon(n: pypsa.Network) -> pd.DataFrame:
    """cost_recovery() plus the carbon cost the CO2 cap's shadow price puts on gas.

    The cap's dual is an implicit carbon price the generator pays through the market;
    without it gas would look like it over-recovers."""
    cr = finance.cost_recovery(n).reindex(TECHS).fillna(0.0)
    cr["carbon"] = 0.0
    cr.loc["CCGT", "carbon"] = co2_price(n) * BASE.emissions_t(n)
    cr["cost"] = cr["capex"] + cr["opex"] + cr["carbon"]
    cr["ratio"] = cr["revenue"] / cr["cost"].where(cr["cost"] > 0)
    return cr


def revenue_split(n: pypsa.Network) -> pd.DataFrame:
    """Per generator carrier: margin in scarcity hours (price above the gas level, set by
    lost load or storage) vs infra-marginal rent in ordinary hours; gas margin is net of carbon."""
    w = n.snapshot_weightings.generators
    price = n.buses_t.marginal_price["electricity"]
    scarcity = price > gas_price_level(n) + 1e-3
    p = names.plain(n.generators_t.p).mul(w, axis=0)
    rows = {}
    for g in ("onwind", "solar", "CCGT"):
        mc = names.plain(n.generators.marginal_cost)[g] + (co2_price(n) * BASE.CO2_CCGT if g == "CCGT" else 0.0)
        margin = (price - mc) * p[g]
        rows[g] = {"scarcity rent": float(margin[scarcity].sum()), "infra-marginal rent": float(margin[~scarcity].sum())}
    return pd.DataFrame(rows).T


def numbers(n: pypsa.Network) -> dict:
    w = n.snapshot_weightings.generators
    price = n.buses_t.marginal_price["electricity"]
    load = n.loads_t.p_set["demand"]
    cr = costs_with_carbon(n)
    supply = finance.by_carrier(n.statistics.supply(comps=["Generator"]))
    mv = finance.by_carrier(n.statistics.market_value(comps=["Generator"]))
    gas_level = gas_price_level(n)
    hours = float(w.sum())
    price_levels = {
        "zero": float(w[price.abs() < 1e-3].sum() / hours * 100),
        "gas_marginal": float(w[(price - gas_level).abs() < 1e-3].sum() / hours * 100),
        "scarcity": float(w[price > gas_level + 1e-3].sum() / hours * 100),
        "other": float(w[(price.abs() >= 1e-3) & (price < gas_level - 1e-3)].sum() / hours * 100),
    }
    return {
        "co2_price_eur_t": co2_price(n),
        "gas_price_level_eur_mwh": gas_level,
        "carbon_cost_ccgt_meur_a": float(cr.loc["CCGT", "carbon"] / 1e6),
        "cost_recovery_ratio": {t: float(cr.loc[t, "ratio"]) if cr.loc[t, "cost"] > 0 else None for t in TECHS},
        "zero_profit_residual_pct": {t: float(100 * (cr.loc[t, "revenue"] - cr.loc[t, "cost"]) / cr.loc[t, "cost"]) if cr.loc[t, "cost"] > 0 else None for t in TECHS},
        "revenue_meur_a": {t: float(cr.loc[t, "revenue"] / 1e6) for t in TECHS},
        "annualised_cost_meur_a": {t: float(cr.loc[t, "cost"] / 1e6) for t in TECHS},
        "market_value_eur_mwh": {t: float(mv.get(t, float("nan"))) for t in ("onwind", "solar", "CCGT")},
        "lcoe_eur_mwh": {t: finance.lcoe(float(cr.loc[t, "cost"]), float(supply.get(t, 0.0))) for t in ("onwind", "solar", "CCGT")},
        "share_of_hours_pct": price_levels,
        "mean_price_eur_mwh": float((price * w).sum() / hours),
        "load_weighted_price_eur_mwh": float((price * load * w).sum() / (load * w).sum()),
        "max_price_eur_mwh": float(price.max()),
        "consumer_payment_meur_a": float((price * load * w).sum() / 1e6),
        "system_cost_meur_a": float(n.objective / 1e6),
        "scarcity_hours_h": float(w[price > gas_level + 1e-3].sum()),
        "gas_scarcity_margin_eur_per_mw_a": float(((price - gas_level).clip(lower=0) * w).sum()),
        "gas_capital_cost_eur_per_mw_a": float(names.plain(n.generators.capital_cost)["CCGT"]),
        "scarcity_rent_share_pct": {g: float(100 * r["scarcity rent"] / (r["scarcity rent"] + r["infra-marginal rent"])) if (r["scarcity rent"] + r["infra-marginal rent"]) > 0 else None for g, r in revenue_split(n).iterrows()},
    }


def margin_intuition(n: pypsa.Network) -> bundle.Figure:
    """The price duration curve against the price gas sets: the area above that level is
    what a MW of gas earns over its running cost, and it equals the MW's annualised cost."""
    w = n.snapshot_weightings.generators
    price = n.buses_t.marginal_price["electricity"]
    level = gas_price_level(n)
    order = price.sort_values(ascending=False).index
    hours = w[order].cumsum()
    xs: list[float] = [0.0]
    ys: list[float] = [float(price[order[0]])]
    for h0, h1, v in zip([0.0, *hours.iloc[:-1]], hours, price[order]):
        # one step per snapshot, merged while the price holds
        if abs(v - ys[-1]) > 1e-6:
            xs.append(float(h0)); ys.append(float(v))
        xs.append(float(h1)); ys.append(float(v))
    view = 3500.0  # the rest of the year sits at zero
    keep = [i for i, x in enumerate(xs) if x <= view]
    xs, ys = [xs[i] for i in keep] + [view], [ys[i] for i in keep] + [ys[keep[-1] + 1] if keep[-1] + 1 < len(ys) else 0.0]
    above = [i for i, y in enumerate(ys) if y > level + 1e-3]
    ax = [xs[i] for i in above] + [xs[above[-1] + 1]]
    ay = [ys[i] for i in above] + [ys[above[-1]]]
    margin = float(((price - level).clip(lower=0) * w).sum())
    capital = float(names.plain(n.generators.capital_cost)["CCGT"])
    scarce = float(w[price > level + 1e-3].sum())
    option, ds = charts.xy_areas(
        [charts.Curve("price, sorted", xs, ys, color=cs.NEUTRAL, width=2.5),
         charts.Curve("price when gas sets it (fuel plus CO2)", [0.0, view], [level, level], color="#0072b2", dashed=True)],
        [charts.Area("what a MW of gas earns above its running cost", ax, [level] * len(ax), ay, charts.BAND_BELOW)],
        x_name="Hours of the year, dearest first",
        units="EUR/MWh",
        x_max=view,
    )
    return bundle.Figure(
        option, ds, title="The few hours that pay for the plants",
        caption=f"Every hour of the year sorted by price, dearest first; the remaining {8760 - view:,.0f} hours sit at zero. "
        f"Gas sets {level:.0f} EUR/MWh when it runs. In the {scarce:.0f} scarcity hours the price climbs above that, and "
        f"the green area, {margin:,.0f} EUR per MW of gas, is exactly the {capital:,.0f} EUR a MW costs to build per year.",
    )


def figures(n: pypsa.Network) -> dict[str, bundle.Figure]:
    price = n.buses_t.marginal_price["electricity"]
    option, ds = charts.duration_curves({"price": price}, "EUR/MWh")
    option["yAxis"]["type"] = "log"
    option["yAxis"]["min"] = 1
    option["yAxis"].pop("splitLine", None)
    pdc = bundle.Figure(option, ds, title="Price duration curve (log scale)",
                        caption="A handful of scarcity hours at the value of lost load, a block at the gas marginal cost "
                        "plus its CO2 shadow price, and a long tail at zero when wind and solar are surplus. "
                        "Prices below 1 EUR/MWh are cut off by the log axis.")
    cr = costs_with_carbon(n)
    built = [t for t in TECHS if cr.loc[t, "cost"] > 1e3]
    option, ds = charts.bars(built, {"revenue": (cr.loc[built, "revenue"] / 1e6).round(3).tolist(),
                                     "capex": (cr.loc[built, "capex"] / 1e6).round(3).tolist(),
                                     "opex": (cr.loc[built, "opex"] / 1e6).round(3).tolist(),
                                     "carbon": (cr.loc[built, "carbon"] / 1e6).round(3).tolist()}, "MEUR/a", category_name="technology")
    for s_ in option["series"]:
        if s_["name"] != "revenue":
            s_["stack"] = "cost"
    rc = bundle.Figure(option, ds, title="Revenue against annualised cost",
                       caption="Revenue beside the stacked cost (capital, fuel, and for gas the CO2 shadow price on "
                       "its emissions). Every technology the optimiser built recovers its cost exactly: the "
                       "zero-profit condition of a linear programme. Storage and hydrogen earn on price spreads.")
    split = revenue_split(n) / 1e6
    option, ds = charts.bars(list(split.index), {c: split[c].round(3).tolist() for c in split.columns}, "MEUR/a", stack=True, category_name="technology")
    rs = bundle.Figure(option, ds, title="Where the margin comes from",
                       caption="Margin above marginal cost (gas net of carbon) split into scarcity hours, when the price "
                       "is above the gas level and set by storage or lost load, and ordinary hours.")
    return {"margin_intuition": margin_intuition(n), "price_duration": pdc, "revenue_vs_cost": rc, "revenue_split": rs}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    n = solve(build())
    nums = numbers(n)
    figs = figures(n)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
