# SPDX-License-Identifier: MIT
"""ev-charging-v2g: a fleet of electric vehicles on a market bus, charged three ways.

The fleet is one big battery that is only plugged in at night and around midday and
must deliver a fixed driving demand in the morning and evening commutes. Uncontrolled
charging takes power the moment the cars plug in; smart charging waits for the cheap
hours; vehicle-to-grid also sells back at the evening peak. Same week, same cars, same
prices to start from.
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

SLUG = "ev-charging-v2g"
TITLE = "Electric vehicles: uncontrolled, smart and vehicle-to-grid charging"

FLEET = {"nuclear": (2000, 10), "lignite": (2500, 25), "CCGT": (3000, 55), "OCGT": (3000, 110)}
WIND_MW = 6000
BASE_MW, PEAK_MW = 5000, 10000
DAYS = 7
N_EV = 100_000
EV_KWH, CHARGER_KW, DRIVE_KWH_PER_DAY = 40, 11, 10
EV_STORE_MWH = N_EV * EV_KWH / 1e3  # 4000 MWh
CHARGER_MW = N_EV * CHARGER_KW / 1e3  # 1100 MW
DRIVE_MWH_PER_DAY = N_EV * DRIVE_KWH_PER_DAY / 1e3  # 1000 MWh
DRIVING_HOURS = [7, 8, 17, 18]  # the commutes; the cars are on the road, not plugged in
PLUGGED_HOURS = list(range(19, 24)) + list(range(0, 7)) + [11, 12, 13]
MIN_SOC = 0.2
EFF = 0.9
CASES = ["uncontrolled", "smart", "vehicle-to-grid"]


def _profiles(index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    hour = index.hour
    weekend = index.dayofweek >= 5
    plugged = np.where(weekend, 1.0, np.isin(hour, PLUGGED_HOURS).astype(float))
    driving = np.where(weekend, 0.0, np.isin(hour, DRIVING_HOURS).astype(float))
    driving = driving * DRIVE_MWH_PER_DAY / len(DRIVING_HOURS)
    return pd.Series(plugged, index=index, name="plugged"), pd.Series(driving, index=index, name="driving")


def uncontrolled_schedule(plugged: pd.Series, driving: pd.Series) -> tuple[pd.Series, float]:
    """Hour-by-hour: drive, then charge at full power while plugged in and not full.

    Starts the week with a full fleet and returns the grid draw per hour (MW) and the
    starting energy, so the store can be initialised to match.
    """
    soc = EV_STORE_MWH
    draw = []
    for plug, drive in zip(plugged.to_numpy(), driving.to_numpy()):
        soc -= drive
        charge = min(CHARGER_MW * EFF, EV_STORE_MWH - soc) if plug > 0 else 0.0
        soc += charge
        draw.append(charge / EFF)
    return pd.Series(draw, index=plugged.index, name="draw"), EV_STORE_MWH


def build(*, case: str = "smart") -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(DAYS))
    n.add("Carrier", list(FLEET) + ["onwind", "EV battery", "load shedding", "AC", "battery charger", "battery discharger"])
    n.add("Bus", "grid", carrier="AC")
    n.add("Bus", "EV", carrier="EV battery")
    for carrier, (p_nom, mc) in FLEET.items():
        n.add("Generator", carrier, bus="grid", carrier=carrier, p_nom=p_nom, marginal_cost=mc)
    n.add("Generator", "onwind", bus="grid", carrier="onwind", p_nom=WIND_MW, p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", "load shedding", bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=3000)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW))
    plugged, driving = _profiles(n.snapshots)
    n.add("Load", "driving", bus="EV", carrier="EV battery", p_set=driving)
    if case == "uncontrolled":
        # the charging schedule is not a decision: full power whenever plugged in until full,
        # simulated hour by hour and then fixed on the charger (p_min_pu = p_max_pu)
        draw, e_initial = uncontrolled_schedule(plugged, driving)
        n.add("Store", "EV battery", bus="EV", carrier="EV battery", e_nom=EV_STORE_MWH, e_initial=e_initial, e_min_pu=MIN_SOC)
        n.add("Link", "battery charger", bus0="grid", bus1="EV", carrier="battery charger", p_nom=CHARGER_MW,
              efficiency=EFF, p_max_pu=draw / CHARGER_MW, p_min_pu=draw / CHARGER_MW)
        return n
    n.add("Store", "EV battery", bus="EV", carrier="EV battery", e_nom=EV_STORE_MWH, e_cyclic=True, e_min_pu=MIN_SOC)
    n.add("Link", "battery charger", bus0="grid", bus1="EV", carrier="battery charger", p_nom=CHARGER_MW,
          efficiency=EFF, p_max_pu=plugged)
    if case == "vehicle-to-grid":
        n.add("Link", "battery discharger", bus0="EV", bus1="grid", carrier="battery discharger", p_nom=CHARGER_MW,
              efficiency=EFF, p_max_pu=plugged, marginal_cost=0.5)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def cases() -> dict[str, pypsa.Network]:
    return {c: solve(build(case=c)) for c in CASES}


def _summary(n: pypsa.Network, case: str) -> dict:
    price = n.buses_t.marginal_price["grid"]
    charge = n.links_t.p0["battery charger"]  # MW drawn from the grid
    discharge = -n.links_t.p1["battery discharger"] if "battery discharger" in n.links.index else pd.Series(0.0, index=n.snapshots)
    load = n.loads_t.p_set["demand"]
    net = load + charge - discharge
    driving = n.loads_t.p_set["driving"].sum()
    gen_cost = float(sum((n.generators_t.p[g] * n.generators.marginal_cost[g]).sum() for g in n.generators.index))
    return {
        "system_cost_eur": gen_cost,
        "charging_cost_eur": float((price * charge).sum()),
        "v2g_revenue_eur": float((price * discharge).sum()),
        "net_ev_cost_eur": float((price * (charge - discharge)).sum()),
        "avg_charging_price_eur_mwh": float((price * charge).sum() / charge.sum()) if charge.sum() > 0 else None,
        "peak_load_increase_mw": float(net.max() - load.max()),
        "peak_price_eur_mwh": float(price.max()),
        "charged_mwh": float(charge.sum() * EFF),
        "discharged_to_grid_mwh": float(discharge.sum()),
        "cycles": float((driving + discharge.sum() / EFF) / EV_STORE_MWH),
    }


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    out = {c: _summary(n, c) for c, n in nets.items()}
    base = out["uncontrolled"]["system_cost_eur"]
    out["system_cost_saving_vs_uncontrolled_eur"] = {c: base - out[c]["system_cost_eur"] for c in CASES if c != "uncontrolled"}
    out["fleet"] = {"vehicles": N_EV, "battery_mwh": EV_STORE_MWH, "charger_mw": CHARGER_MW, "driving_mwh_per_weekday": DRIVE_MWH_PER_DAY}
    return out


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    smart = nets["smart"]
    df = pd.DataFrame({c: nets[c].links_t.p0["battery charger"].round(1) for c in CASES})
    df["vehicle-to-grid"] = (nets["vehicle-to-grid"].links_t.p0["battery charger"] + nets["vehicle-to-grid"].links_t.p1["battery discharger"]).round(1)
    df["price"] = smart.buses_t.marginal_price["grid"].round(2)
    option, ds = charts.dual_axis(df, CASES, ["price"], "MW from the grid", "EUR/MWh", step="middle")
    ch = bundle.Figure(option, ds, title="Charging power against the price",
                       caption="Grid draw of the fleet per case (vehicle-to-grid shown net, negative when selling back) "
                       "with the smart-case price on the right axis. Uncontrolled charging lands on the evening "
                       "peak; smart charging waits for the night trough; V2G discharges into the peak.")
    soc = pd.DataFrame({c: (nets[c].stores_t.e["EV battery"] / EV_STORE_MWH * 100).round(1) for c in CASES})
    option, ds = charts.time_series(soc, "% of fleet battery")
    option["yAxis"]["min"] = 0
    option["yAxis"]["max"] = 100
    soc_fig = bundle.Figure(option, ds, title="Fleet state of charge",
                            caption="Uncontrolled charging keeps the cars full; smart charging rides closer to the "
                            "20 % floor and fills up in the cheap hours; V2G cycles the batteries harder.")
    s = {c: _summary(nets[c], c) for c in CASES}
    option, ds = charts.bars(CASES, {"system dispatch cost": [round(s[c]["system_cost_eur"] / 1e6, 3) for c in CASES],
                                     "EV net charging cost": [round(s[c]["net_ev_cost_eur"] / 1e6, 3) for c in CASES]},
                             "MEUR per week", category_name="case")
    cost = bundle.Figure(option, ds, title="System cost and the fleet's electricity bill",
                         caption="Both fall from uncontrolled to smart to V2G: the fleet buys cheaper hours and, with "
                         "V2G, earns the peak spread back.")
    return {"charging_vs_price": ch, "state_of_charge": soc_fig, "cost_comparison": cost}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = cases()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
