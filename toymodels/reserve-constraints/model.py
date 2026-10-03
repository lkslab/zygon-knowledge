# SPDX-License-Identifier: MIT
"""reserve-constraints: an upward operating reserve added to a dispatch model as a
custom constraint, the `extra_functionality` pattern for anything PyPSA has no
attribute for.

One bus, a thermal fleet and wind over three days. Every hour the committed headroom
must cover 10 % of load plus 20 % of what wind is producing. Reserve is a new variable
per generator, capped by that generator's headroom; the dual of the requirement is the
reserve price, and the extra dispatch cost is what holding it back costs.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, names, profiles, run  # noqa: E402

SLUG = "reserve-constraints"
TITLE = "Operating reserve as a custom constraint"

FLEET = {"nuclear": (2000, 10), "lignite": (2000, 25), "CCGT": (2500, 55), "OCGT": (2500, 110)}
WIND_MW = 6000
BASE_MW, PEAK_MW = 5000, 9500
DAYS = 3
LOAD_SHARE, WIND_SHARE = 0.10, 0.20
PROVIDERS = ["lignite", "CCGT", "OCGT"]  # nuclear and wind hold no reserve


def build() -> pypsa.Network:
    n = pypsa.Network()
    n.set_snapshots(profiles.hourly_index(DAYS))
    n.add("Carrier", list(FLEET) + ["onwind", "load shedding", "AC"])
    n.add("Bus", "grid", carrier="AC")
    for carrier, (p_nom, mc) in FLEET.items():
        n.add("Generator", names.gen(carrier), bus="grid", carrier=carrier, p_nom=p_nom, marginal_cost=mc)
    n.add("Generator", names.gen("onwind"), bus="grid", carrier="onwind", p_nom=WIND_MW, marginal_cost=0, p_max_pu=profiles.wind(n.snapshots))
    n.add("Generator", names.gen("load shedding"), bus="grid", carrier="load shedding", p_nom=1e5, marginal_cost=3000)
    n.add("Load", "demand", bus="grid", carrier="load", p_set=profiles.daily_load(n.snapshots, BASE_MW, PEAK_MW))
    return n


def add_reserve(n: pypsa.Network, sns: pd.Index) -> None:
    """The extra_functionality hook: called with the network after PyPSA built `n.model`
    (a linopy Model) and before it is solved. Adds a reserve variable per snapshot and
    provider, a headroom cap and the requirement."""
    m = n.model
    p = m["Generator-p"]  # dispatch variables, dims (snapshot, name)
    providers = [names.gen(g) for g in PROVIDERS]
    reserve = m.add_variables(lower=0, coords=[sns, pd.Index(providers, name="name")], name="Generator-reserve")
    headroom = n.generators.p_nom[providers]  # p_max_pu is 1 for the thermal fleet
    m.add_constraints(reserve + p.sel(name=providers) <= headroom, name="Generator-reserve-headroom")
    load = n.loads_t.p_set.loc[sns, "demand"]
    m.add_constraints(reserve.sum("name") - WIND_SHARE * p.sel(name=names.gen("onwind")) >= LOAD_SHARE * load,
                      name="Reserve-requirement")


def solve(n: pypsa.Network, *, reserve: bool = True) -> pypsa.Network:
    return run.solve(n, extra_functionality=add_reserve if reserve else None)


def reserve_results(n: pypsa.Network) -> tuple[pd.DataFrame, pd.Series]:
    """Reserve held per provider (MW) and the reserve price (EUR/MW/h) from the model."""
    held = names.plain(n.model["Generator-reserve"].solution.to_pandas())
    price = n.model.constraints["Reserve-requirement"].dual.to_pandas()
    return held, price


def runs() -> dict[str, pypsa.Network]:
    return {"with reserve": solve(build()), "without reserve": solve(build(), reserve=False)}


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    wr, wo = nets["with reserve"], nets["without reserve"]
    held, rprice = reserve_results(wr)
    load = wr.loads_t.p_set["demand"]
    req = LOAD_SHARE * load + WIND_SHARE * wr.generators_t.p[names.gen("onwind")]
    return {
        "reserve_cost_eur": float(wr.objective - wo.objective),
        "reserve_cost_share_pct": float(100 * (wr.objective - wo.objective) / wo.objective),
        "reserve_price_eur_mw_h": {"mean": float(rprice.mean()), "max": float(rprice.max()), "hours_nonzero": int((rprice > 1e-6).sum())},
        "requirement_mw": {"mean": float(req.mean()), "max": float(req.max())},
        "reserve_held_share_pct": {g: float(100 * held[g].sum() / held.sum().sum()) for g in PROVIDERS},
        "avg_price_eur_mwh": {"with reserve": float(wr.buses_t.marginal_price["grid"].mean()), "without reserve": float(wo.buses_t.marginal_price["grid"].mean())},
        "peaker_energy_mwh": {"with reserve": float(wr.generators_t.p[names.gen("OCGT")].sum()), "without reserve": float(wo.generators_t.p[names.gen("OCGT")].sum())},
        "wind_curtailed_mwh": {k: float((n.generators_t.p_max_pu[names.gen("onwind")] * WIND_MW - n.generators_t.p[names.gen("onwind")]).sum()) for k, n in nets.items()},
        "requirement_rule": f"{LOAD_SHARE:.0%} of load + {WIND_SHARE:.0%} of wind output",
    }


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    wr, wo = nets["with reserve"], nets["without reserve"]
    held, rprice = reserve_results(wr)
    stack = names.plain(wr.generators_t.p)[list(FLEET) + ["onwind"]].round(1)
    stack["reserve held"] = held.sum(axis=1).round(1)
    option, ds = charts.time_series(stack, "MW", stack=True, area=True)
    disp = bundle.Figure(option, ds, title="Dispatch with the reserve held on top",
                         caption="Energy dispatch stacked in merit order; the top band is the headroom kept in reserve. "
                         "To hold it, cheaper units run below capacity and the peaker fills in.")
    option, ds = charts.time_series(held[PROVIDERS].round(1), "MW", stack=True, area=True)
    prov = bundle.Figure(option, ds, title="Reserve provision by unit",
                         caption="Who holds the reserve: the unit whose headroom is cheapest to leave idle, so the "
                         "mid-merit units by day and the peaker when they are loaded.")
    prices = pd.DataFrame({"with reserve": wr.buses_t.marginal_price["grid"].round(2),
                           "without reserve": wo.buses_t.marginal_price["grid"].round(2),
                           "reserve price": rprice.round(2)})
    option, ds = charts.time_series(prices, "EUR/MWh", step="end")
    pr = bundle.Figure(option, ds, title="Energy price with and without reserve, and the reserve price",
                       caption="The reserve requirement's dual is the reserve price: zero when headroom is free, "
                       "positive in the hours where holding it forces a dearer unit into the energy stack.")
    return {"dispatch_with_reserve": disp, "reserve_provision": prov, "prices": pr}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
