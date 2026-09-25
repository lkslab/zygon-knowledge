# SPDX-License-Identifier: MIT
"""Carrier ids the toy models use as series names, with the app's colours.

The ids are pypsa-eur carrier ids, the keys of pypsa-app's
`frontend/app/src/lib/registry/pypsa-eur-style.json`, so the app colours a series
named `CCGT` or `onwind` on its own. The colours below are a snapshot of that file
(2026-09) used only by the standalone `preview.html`; a figure.json never carries
them. A series named outside this table (a scenario, a stage, a metric) is drawn
from the Okabe-Ito scenario palette instead, in the order it appears.
"""

from __future__ import annotations

CARRIERS: dict[str, tuple[str, str]] = {
    # id: (nice name, colour)
    "nuclear": ("Nuclear", "#ff8c00"),
    "lignite": ("Lignite", "#826837"),
    "coal": ("Coal", "#545454"),
    "CCGT": ("Combined-cycle gas", "#a85522"),
    "OCGT": ("Open-cycle gas", "#e0986c"),
    "gas": ("Gas", "#e05b09"),
    "oil": ("Oil", "#c9c9c9"),
    "onwind": ("Onshore wind", "#235ebc"),
    "offwind-ac": ("Offshore wind", "#6895dd"),
    "solar": ("Solar", "#f9d002"),
    "hydro": ("Reservoir hydro", "#298c81"),
    "ror": ("Run of river", "#3dbfb0"),
    "PHS": ("Pumped hydro", "#51dbcc"),
    "battery": ("Battery", "#ace37f"),
    "battery charger": ("Battery charging", "#88a75b"),
    "battery discharger": ("Battery discharging", "#5d4e29"),
    "H2": ("Hydrogen", "#bf13a0"),
    "H2 Electrolysis": ("Electrolysis", "#ff29d9"),
    "H2 Fuel Cell": ("Fuel cell", "#c251ae"),
    "H2 Store": ("Hydrogen store", "#bf13a0"),
    "AC": ("AC line", "#70af1d"),
    "DC": ("DC link", "#8a1caf"),
    "transmission lines": ("Transmission", "#6c9459"),
    "electricity": ("Electricity", "#110d63"),
    "load": ("Electricity demand", "#110d63"),
    "load shedding": ("Load shedding", "#dd2e23"),
    "heat": ("Heat", "#cc1f1f"),
    "heat pump": ("Heat pump", "#2fb537"),
    "gas boiler": ("Gas boiler", "#db6a25"),
    "water tanks": ("Water tank", "#e69487"),
    "resistive heater": ("Resistive heater", "#d8f9b8"),
    "CHP": ("CHP", "#8a5751"),
    "biomass": ("Biomass", "#baa741"),
    "solid biomass": ("Solid biomass", "#baa741"),
    "co2": ("CO2", "#f29dae"),
    "co2 stored": ("CO2 captured", "#f2385a"),
    "co2 sequestered": ("CO2 sequestered", "#f2682f"),
    "DAC": ("Direct air capture", "#ff5270"),
    "methanolisation": ("Methanol synthesis", "#83d6d5"),
    "methanol": ("Methanol", "#FF7B00"),
    "EV battery": ("EV battery", "#baf238"),
    "BEV charger": ("EV charger", "#baf238"),
    "V2G": ("Vehicle-to-grid", "#e5ffa8"),
}

# Non-carrier series (scenarios, stages, metrics): Okabe-Ito, colour-blind safe, the
# same tuple as pypsa-app's `SCENARIO_PALETTE`.
SCENARIO_PALETTE: tuple[str, ...] = (
    "#0072b2",
    "#e69f00",
    "#009e73",
    "#cc79a7",
    "#56b4e9",
    "#d55e00",
    "#f0e442",
    "#8c8c8c",
)

# A mid grey that reads on both themes: zero lines, reference lines, marks.
NEUTRAL = "#6b7280"


def is_carrier(name: str) -> bool:
    return name in CARRIERS


def colour(name: str) -> str | None:
    entry = CARRIERS.get(name)
    return entry[1] if entry else None


def nice_name(name: str) -> str:
    entry = CARRIERS.get(name)
    return entry[0] if entry else name
