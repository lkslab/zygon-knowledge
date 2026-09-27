# SPDX-License-Identifier: MIT
"""stochastic-cvar: investment under an uncertain gas price, risk-neutral and risk-averse.

One node, wind, solar, gas and a battery, two representative fortnights. The gas price
is unknown when capacities are chosen: low, mid or high with given probabilities.
Three deterministic plans (one per price), a two-stage stochastic plan that minimises
expected cost, and CVaR-weighted plans that also penalise the expensive tail. The
value of the stochastic solution and the expected value of perfect information fall
out of comparing them.
"""

from __future__ import annotations

import functools
import sys
import time
from pathlib import Path

import pandas as pd
import pypsa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import bundle, charts, finance, profiles, run  # noqa: E402

SLUG = "stochastic-cvar"
TITLE = "Stochastic investment and CVaR risk aversion"

BASE = run.load_model("capacity-expansion-single-node")
TECH = BASE.TECH
MEAN_LOAD_MW = 100
GAS_PRICE = {"low": 40.0, "mid": 80.0, "high": 160.0}  # EUR/MWh_el marginal cost of CCGT
PROB = {"low": 0.3, "mid": 0.4, "high": 0.3}
ALPHA = 0.9
OMEGAS = [0.0, 0.25, 0.5, 0.75, 1.0]
CVAR_OMEGA = 0.5
CARRIERS = ["onwind", "solar", "CCGT", "battery"]


def _capex(tech: str) -> float:
    t = TECH[tech]
    return finance.capital_cost(t["overnight"], t["life"], fom_pct=t["fom"])


def build(*, gas_price: float = GAS_PRICE["mid"], scenarios: dict[str, float] | None = None,
          risk: tuple[float, float] | None = None, fixed: pd.Series | None = None) -> pypsa.Network:
    """Deterministic (`gas_price`) or stochastic (`scenarios` = probability per scenario name).

    `risk=(alpha, omega)` switches on CVaR; `fixed` freezes capacities (a Series by carrier)
    to evaluate a plan under other prices.
    """
    index, weight = profiles.representative_weeks()
    year = profiles.year_index()
    n = pypsa.Network()
    n.set_snapshots(index)
    n.snapshot_weightings.loc[:, :] = weight
    n.add("Carrier", ["AC", "load shedding", "onwind", "solar", "battery"])
    n.add("Carrier", "CCGT", co2_emissions=BASE.CO2_CCGT)
    n.add("Bus", "electricity", carrier="AC")
    n.add("Load", "demand", bus="electricity", carrier="load", p_set=profiles.annual_load(year, MEAN_LOAD_MW).loc[index])
    ext = fixed is None
    n.add("Generator", "onwind", bus="electricity", carrier="onwind", p_nom_extendable=ext, capital_cost=_capex("onwind"),
          p_max_pu=profiles.wind(year).loc[index], p_nom=0 if ext else fixed["onwind"])
    n.add("Generator", "solar", bus="electricity", carrier="solar", p_nom_extendable=ext, capital_cost=_capex("solar"),
          p_max_pu=profiles.solar(year).loc[index], p_nom=0 if ext else fixed["solar"])
    n.add("Generator", "CCGT", bus="electricity", carrier="CCGT", p_nom_extendable=ext, capital_cost=_capex("CCGT"),
          marginal_cost=gas_price, p_nom=0 if ext else fixed["CCGT"])
    n.add("Generator", "load shedding", bus="electricity", carrier="load shedding", p_nom=1e6, marginal_cost=BASE.VOLL)
    b = TECH["battery"]
    n.add("StorageUnit", "battery", bus="electricity", carrier="battery", p_nom_extendable=ext, capital_cost=_capex("battery"),
          max_hours=b["max_hours"], efficiency_store=b["eta"], efficiency_dispatch=b["eta"], cyclic_state_of_charge=True,
          p_nom=0 if ext else fixed["battery"])
    if scenarios:
        n.set_scenarios(scenarios)
        for sc in scenarios:
            n.generators.loc[(sc, "CCGT"), "marginal_cost"] = GAS_PRICE[sc]
        if risk:
            n.set_risk_preference(*risk)
    return n


def solve(n: pypsa.Network) -> pypsa.Network:
    return run.solve(n)


def capacities(n: pypsa.Network) -> pd.Series:
    g = n.generators.p_nom_opt
    s = n.storage_units.p_nom_opt
    if isinstance(g.index, pd.MultiIndex):
        first = g.index.get_level_values(0)[0]
        g, s = g.xs(first, level="scenario"), s.xs(first, level="scenario")
    return pd.Series({"onwind": g["onwind"], "solar": g["solar"], "CCGT": g["CCGT"], "battery": s["battery"]})


def realised_costs(n: pypsa.Network) -> dict[str, dict[str, float]]:
    """Per scenario: annualised capex (shared) and the opex realised under that scenario's prices."""
    cap = capacities(n)
    capex = sum(cap[c] * _capex(c) for c in CARRIERS)
    w = n.snapshot_weightings.generators
    out: dict[str, dict[str, float]] = {}
    p = n.generators_t.p
    if isinstance(p.columns, pd.MultiIndex):
        for sc in p.columns.get_level_values(0).unique():
            gas = float(n.generators.loc[(sc, "CCGT"), "marginal_cost"])
            shed = float(n.generators.loc[(sc, "load shedding"), "marginal_cost"])
            opex = float((p[(sc, "CCGT")] * gas * w).sum() + (p[(sc, "load shedding")] * shed * w).sum())
            out[str(sc)] = {"capex": float(capex), "opex": opex, "total": float(capex) + opex}
    else:
        gas = float(n.generators.loc["CCGT", "marginal_cost"])
        opex = float((p["CCGT"] * gas * w).sum() + (p["load shedding"] * BASE.VOLL * w).sum())
        out["realised"] = {"capex": float(capex), "opex": opex, "total": float(capex) + opex}
    return out


def evaluate_plan(cap: pd.Series) -> dict[str, float]:
    """Cost of a fixed plan under every scenario's gas price (dispatch only)."""
    out = {}
    for sc, price in GAS_PRICE.items():
        m = solve(build(gas_price=price, fixed=cap))
        out[sc] = realised_costs(m)["realised"]["total"]
    return out


def runs() -> dict[str, pypsa.Network]:
    nets: dict[str, pypsa.Network] = {}
    for sc, price in GAS_PRICE.items():
        nets[f"deterministic {sc}"] = solve(build(gas_price=price))
    nets["risk neutral"] = solve(build(scenarios=PROB))
    nets[f"cvar {CVAR_OMEGA}"] = solve(build(scenarios=PROB, risk=(ALPHA, CVAR_OMEGA)))
    return nets


@functools.lru_cache(maxsize=1)
def omega_sweep() -> pd.DataFrame:
    rows = []
    for om in OMEGAS:
        n = solve(build(scenarios=PROB, risk=(ALPHA, om) if om > 0 else None))
        rc = realised_costs(n)
        expected = sum(PROB[s] * rc[s]["total"] for s in PROB)
        worst = max(rc[s]["total"] for s in PROB)
        cap = capacities(n)
        rows.append({"omega": om, "expected cost": expected / 1e6, "worst-case cost": worst / 1e6,
                     **{f"cap_{c}": float(cap[c]) for c in CARRIERS}})
    return pd.DataFrame(rows).set_index("omega")


def numbers(nets: dict[str, pypsa.Network]) -> dict:
    det = {sc: nets[f"deterministic {sc}"] for sc in GAS_PRICE}
    sp = nets["risk neutral"]
    cv = nets[f"cvar {CVAR_OMEGA}"]
    ws = sum(PROB[s] * det[s].objective for s in PROB)  # wait-and-see: perfect information
    sp_cost = float(sp.objective)
    mid_plan = evaluate_plan(capacities(det["mid"]))
    eev = sum(PROB[s] * mid_plan[s] for s in PROB)
    rc_sp, rc_cv = realised_costs(sp), realised_costs(cv)
    exp_cv = sum(PROB[s] * rc_cv[s]["total"] for s in PROB)
    sweep = omega_sweep()
    return {
        "capacity_mw": {name: {c: float(capacities(n)[c]) for c in CARRIERS} for name, n in nets.items()},
        "expected_cost_meur_a": {"wait_and_see": ws / 1e6, "stochastic": sp_cost / 1e6, "mid_plan_eev": eev / 1e6, "cvar": exp_cv / 1e6},
        "evpi_meur_a": (sp_cost - ws) / 1e6,
        "vss_meur_a": (eev - sp_cost) / 1e6,
        "cvar_premium_meur_a": (exp_cv - sp_cost) / 1e6,
        "worst_case_cost_meur_a": {"stochastic": max(rc_sp[s]["total"] for s in PROB) / 1e6, "cvar": max(rc_cv[s]["total"] for s in PROB) / 1e6},
        "cost_by_scenario_meur_a": {"stochastic": {s: rc_sp[s]["total"] / 1e6 for s in PROB}, "cvar": {s: rc_cv[s]["total"] / 1e6 for s in PROB}, "mid_plan": {s: mid_plan[s] / 1e6 for s in PROB}},
        "omega_sweep": {str(om): {"expected_cost_meur_a": float(r["expected cost"]), "worst_case_meur_a": float(r["worst-case cost"]), "ccgt_mw": float(r["cap_CCGT"]), "onwind_mw": float(r["cap_onwind"])} for om, r in sweep.iterrows()},
        "alpha": ALPHA,
        "probabilities": PROB,
        "gas_price_eur_mwh": GAS_PRICE,
    }


def figures(nets: dict[str, pypsa.Network]) -> dict[str, bundle.Figure]:
    labels = list(nets)
    caps = pd.DataFrame({name: capacities(n) for name, n in nets.items()}).round(1)
    option, ds = charts.bars(labels, {c: caps.loc[c].tolist() for c in CARRIERS}, "MW", stack=True, horizontal=False, category_name="plan")
    mix = bundle.Figure(option, ds, title="Capacity by planning strategy",
                        caption="Each deterministic plan bets on one gas price. The stochastic plan hedges; the "
                        "CVaR plan hedges harder, buying more wind and less gas to cap the expensive tail.")
    det_mid = evaluate_plan(capacities(nets["deterministic mid"]))
    rc_sp, rc_cv = realised_costs(nets["risk neutral"]), realised_costs(nets[f"cvar {CVAR_OMEGA}"])
    scen = list(PROB)
    option, ds = charts.bars(scen, {"mid-price plan": [round(det_mid[s] / 1e6, 2) for s in scen],
                                    "risk neutral": [round(rc_sp[s]["total"] / 1e6, 2) for s in scen],
                                    f"cvar {CVAR_OMEGA}": [round(rc_cv[s]["total"] / 1e6, 2) for s in scen]}, "MEUR/a", category_name="gas price scenario")
    dist = bundle.Figure(option, ds, title="Realised annual cost under each gas price",
                         caption="What each plan costs once the price is revealed. The CVaR plan pays a little more "
                         "in the cheap scenarios to be cheaper in the expensive one.")
    sweep = omega_sweep()[["expected cost", "worst-case cost"]].round(3)
    option, ds = charts.xy_lines(sweep, "CVaR weight omega", "MEUR/a", symbols=True, x_extra={"min": 0, "max": 1})
    om = bundle.Figure(option, ds, title="Expected vs worst-case cost as risk aversion grows",
                       caption="omega = 0 is the risk-neutral plan; omega = 1 minimises the tail alone. Expected cost "
                       "rises monotonically, the worst case falls: the price of insurance.")
    return {"cost_distribution": dist, "capacity_mix_by_strategy": mix, "omega_sweep": om}


def main(outdir: Path | None = None, runtime_start: float | None = None) -> dict:
    t0 = runtime_start or time.perf_counter()
    nets = runs()
    nums = numbers(nets)
    figs = figures(nets)
    run.emit(SLUG, figs, nums, title=TITLE, subtitle=__doc__.split("\n\n")[1].strip(), runtime_s=time.perf_counter() - t0, outdir=outdir)
    return nums


if __name__ == "__main__":
    main()
