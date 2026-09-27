# SPDX-License-Identifier: MIT
"""line-loading-limits: a line whose rating changes with the hour, and what a static
rating, a dynamic rating and a short emergency allowance each cost.

Two buses, cheap generation on one side, the load and a peaker on the other, one line
between them over three hot days. The conductor carries less in the afternoon heat and
more at night. Three cases: the conservative static rating (the afternoon value all
day), the dynamic rating that follows the hour, and the dynamic rating with a two-hour
emergency allowance at the evening peak.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, profiles, run  # noqa: E402

SLUG = "line-loading-limits"
TITLE = "Static, dynamic and emergency line ratings"

DAYS = 3
S_NOM = 1000  # MW nameplate (cold) rating
HOT_PU, HOT_HOURS = 0.8, range(12, 19)  # afternoon derating
EMERGENCY_PU, EMERGENCY_HOURS = 1.1, range(18, 20)  # short-term allowance at the evening peak
BASE_MW, PEAK_MW = 600, 1700
CHEAP = dict(carrier="coal", p_nom=2000, marginal_cost=20)
PEAKER = dict(carrier="OCGT", p_nom=1500, marginal_cost=120)


def rating(index: pd.DatetimeIndex, *, dynamic: bool, emergency: bool) -> pd.Series:
    """The per-unit rating series for a case."""
    hours = index.hour.to_numpy()
    if not dynamic:
        return pd.Series(HOT_PU, index=index)
    pu = np.where(np.isin(hours, list(HOT_HOURS)), HOT_PU, 1.0)
    if emergency:
        pu = np.where(np.isin(hours, list(EMERGENCY_HOURS)), EMERGENCY_PU, pu)
    return pd.Series(pu, index=index)


def build(*, dynamic: bool = True, emergency: bool = False) -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(DAYS))
    n.add("Carrier", ["AC", "coal", "OCGT", "load shedding"])
    n.add("Bus", ["A", "B"], v_nom=380, carrier="AC")
    n.add("Generator", "coal A", bus="A", **CHEAP)
    n.add("Generator", "OCGT B", bus="B", **PEAKER)
    n.add("Generator", "shed B", bus="B", carrier="load shedding", p_nom=1e5, marginal_cost=3000)
    n.add("Load", "load B", bus="B", carrier="load", p_set=profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW, noise=0.0))
    n.add("Line", "A-B", bus0="A", bus1="B", x=0.1, r=0.01, s_nom=S_NOM, carrier="AC",
          s_max_pu=rating(n.snapshots, dynamic=dynamic, emergency=emergency))
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


CASES = {"static rating": dict(dynamic=False, emergency=False),
         "dynamic rating": dict(dynamic=True, emergency=False),
         "dynamic + emergency": dict(dynamic=True, emergency=True)}


def runs() -> dict[str, pypsa.Network]:
    return {k: solve(build(**kw)) for k, kw in CASES.items()}


def summary(n: pypsa.Network) -> dict:
    flow = n.lines_t.p0["A-B"]
    limit = n.lines_t.s_max_pu["A-B"] * S_NOM
    price = n.buses_t.marginal_price
    spread = price["B"] - price["A"]
    return {
        "cost_eur": float(n.objective),
        "hours_at_limit": int((flow.abs() >= limit - 1e-3).sum()),
        "congestion_rent_eur": float((flow * spread).sum()),
        "mean_price_spread_eur_mwh": float(spread.mean()),
        "peaker_energy_mwh": float(n.generators_t.p["OCGT B"].sum()),
        "energy_over_line_mwh": float(flow.sum()),
        "load_shed_mwh": float(n.generators_t.p["shed B"].sum()),
    }


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    out = {k: summary(n) for k, n in nets.items()}
    base = out["static rating"]["cost_eur"]
    out["saving_vs_static_eur"] = {k: base - out[k]["cost_eur"] for k in nets if k != "static rating"}
    out["ratings_pu"] = {"night": 1.0, "hot afternoon": HOT_PU, "emergency": EMERGENCY_PU}
    return out


def rating_intuition(nets: dict[str, pypsa.Network]) -> bundle.Figure:
    """The static rating against the one that follows the weather: the static one assumes the
    hottest afternoon all day, the room above it is what cool hours and a short emergency
    allowance add."""
    n = nets["dynamic + emergency"]
    df = pd.DataFrame({"rating": (n.lines_t.s_max_pu["A-B"] * S_NOM).round(1)})
    band = charts.Band(value="rating", level=HOT_PU * S_NOM, level_name="static rating: the hot afternoon all day",
                       below=None, above="room the cooler hours add", unit="MW",
                       value_name="rating that follows the weather", above_color="#56b4e9",
                       under="what the static rating lets through", under_color=charts.BAND_BELOW)
    option, ds = charts.fill_between(df, band, step="end")
    return bundle.Figure(
        option, ds, title="How much a line may carry depends on the weather",
        caption=f"A line's limit is how hot its conductor may get. A static rating of {HOT_PU * S_NOM:.0f} MW assumes the "
        f"hottest afternoon every hour; following the weather it carries {S_NOM} MW at night and in the morning, and "
        f"{EMERGENCY_PU * S_NOM:.0f} MW for two hours at the evening peak under an emergency allowance. The line is full "
        "whenever the peaker would otherwise run, so every extra MW of rating is a MW of cheap power.",
    )


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    df = pd.DataFrame({f"flow, {k}": n.lines_t.p0["A-B"].round(1) for k, n in nets.items()})
    df["limit, dynamic + emergency"] = (nets["dynamic + emergency"].lines_t.s_max_pu["A-B"] * S_NOM).round(1)
    df["limit, static"] = (nets["static rating"].lines_t.s_max_pu["A-B"] * S_NOM).round(1)
    option, ds = charts.time_series(df, "MW", step="end")
    for s in option["series"]:
        if s["name"].startswith("limit"):
            s["lineStyle"] = {**s.get("lineStyle", {}), "type": "dashed"}
    flow = bundle.Figure(option, ds, title="Line flow against its rating",
                         caption="Flow from the cheap side under each rating, with the static limit and the dynamic "
                         "limit dashed. The flow rides the limit whenever the peaker would otherwise run.")
    spread = pd.DataFrame({k: (n.buses_t.marginal_price["B"] - n.buses_t.marginal_price["A"]).round(2) for k, n in nets.items()})
    option, ds = charts.time_series(spread, "EUR/MWh", step="end")
    sp = bundle.Figure(option, ds, title="Price spread across the line",
                       caption="Zero while the line has room; the peaker's cost minus the cheap unit's whenever it is "
                       "full. The dynamic rating removes the spread at night, the emergency allowance at the peak.")
    labels = list(nets)
    s = {k: summary(n) for k, n in nets.items()}
    option, ds = charts.bars(labels, {"dispatch cost": [round(s[k]["cost_eur"] / 1e3, 1) for k in labels],
                                      "congestion rent": [round(s[k]["congestion_rent_eur"] / 1e3, 1) for k in labels]}, "kEUR", category_name="rating")
    bars = bundle.Figure(option, ds, title="Three-day cost and congestion rent by rating",
                         caption="A rating that follows the weather cuts both the dispatch cost and the rent the "
                         "congestion transfers; the emergency allowance trims the last peak hours.")
    return {"rating_intuition": rating_intuition(nets), "flow_vs_limit": flow, "price_spread": sp, "cost_and_rent": bars}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
