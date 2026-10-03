# toymodels/

Minimal, runnable PyPSA models, one directory per concept, for back-of-the-envelope
answers and teaching figures. Nothing here is a study: every model is a few components on
one to four buses with synthetic, seeded inputs, solves in seconds with HiGHS, and writes
its charts in pypsa-app's `figure.json` contract so the app can render them unchanged.

`index.yaml` is the entry point an agent reads: one row per model with its concepts, the
questions it answers, its figure ids and the keys of its headline numbers. From there:

| file | what |
|---|---|
| `<slug>/card.yaml` | the explanation: setup, assumptions, method, knobs, how to read each figure, number definitions, limitations, sources |
| `<slug>/model.py` | the code: `build()`, `solve(n)`, `numbers(n)`, `figures(n)`, `main()`; knobs are keyword arguments of `build()` or module constants |
| `<slug>/results.yaml` | generated: the headline numbers (`numbers`) and run info (`meta`: pypsa version, solver, runtime, figure files) |
| `<slug>/figures/<id>.json` | generated: one ECharts figure bundle per chart, `{version: 1, option, datasets, height}` |
| `<slug>/preview.html` | generated: all of the model's figures on one page, ECharts from a CDN, light/dark toggle, numbers table |
| `_lib/` | shared code: profiles, finance, house-style chart builders, the bundle writers, the runner |

## Running

The models need PyPSA 1.3 and HiGHS; this repo has no environment of its own, so use
pypsa-app's:

```
cd ../pypsa-app && uv run python ../zygon-knowledge/toymodels/_lib/run.py            # all
cd ../pypsa-app && uv run python ../zygon-knowledge/toymodels/_lib/run.py <slug>     # one
```

Outputs are deterministic (seeded profiles, fixed solver settings) and committed, so an
agent can read numbers and figures without running anything. A full run of all 36 models
takes about ten minutes; the year-long expansion, the rolling-horizon pair and the
sampling models are the slow ones, everything else finishes in seconds. After editing a model, rerun
it and commit the regenerated files. Models that build on `capacity-expansion-single-node`
read its `results.yaml` for the unconstrained emissions their caps are fractions of, so
rerun that one first when its inputs change.

## Checks

```
python3 tools/validate.py                                                  # structure: index vs dirs, cards, figures parse
cd ../pypsa-app && uv run python ../zygon-knowledge/tools/check_toymodels.py [--rerun]   # app validator on every figure; --rerun diffs regenerated outputs
```

## Conventions

- **Component names never repeat a carrier id.** PyPSA refuses an `n.add` whose name another
  component type already holds, so a Generator for the Carrier `onwind` is `onwind gen`, a
  Link `<carrier> link`, a Store or StorageUnit `<carrier> unit`, a Bus `<carrier> bus`
  (`_lib/names.py`); carriers keep their pypsa-eur names and figure labels and `numbers`
  keys stay the carrier ids (`names.plain` maps a frame back). Snapshots are integer or
  datetime, never strings.
- **Series names are pypsa-eur carrier ids** (`onwind`, `solar`, `CCGT`, `battery`, `H2
  Electrolysis`, `heat pump`, ...; the table is `_lib/carrier_style.py`). A figure carries
  no colours for them: the app colours by carrier id. Any other series (a scenario, a
  stage, a metric) gets an Okabe-Ito colour in order of appearance.
- **House style** lives in `_lib/charts.py` and mirrors pypsa-app's `figure_templates.py`:
  datasets plus `encode`, no `title` in the option (the card frame owns it), legend below
  the chart, value axis named with its unit, category labels wrap and never rotate, more
  than six categories go horizontal.
- **Figure contract** (`_lib/bundle.py` checks it before writing): version 1, series bind
  to datasets by `datasetId`, no inline `source`, no functions, no `toolbox`/`graphic`,
  height 240..960, at most 50 series, option under 256 KiB. A map figure also carries
  `maps` (named GeoJSON FeatureCollections of named Polygon features) that its `geo`
  component draws on; a builder hands them over as `option["_maps"]`, as it does a height
  as `option["_height"]`.
- **Geography** goes through `charts.region_map`: a made-up country in abstract
  coordinates, split into `Region`s coloured on a diverging scale (purple short of power,
  green with power to spare), with `Site`s (plants, cities), `Link`s (wires, width their
  capacity, vermillion when a flow runs over it) and `Arrow`s (an intent, such as what a
  market plans to move, on the links' width scale). Use it for first principles that are
  about where things are: where power is made and used, why a line congests.
- **Cards** are snake_case YAML with a fixed key set (`id, title, summary, concepts,
  answers, builds_on, setup, method, knobs, figures, numbers, limitations, sources,
  pypsa`) plus two optional keys, `teach` and `pypsa_example`. `id` equals the directory
  name. No `models:`, `version_anchor:` or `schema_version:` keys: these are plain-PyPSA
  models, pinned by `pypsa: "1.3.0"`.
- **`teach`** is the material for an intuition-first explanation, one entry per concept
  the model explains: `{concept, gap, remedy, figure, example?, builds_on_concept?}`. `gap`
  is what goes wrong without the thing, in plain words; `remedy` what it does about it;
  `figure` the card figure that makes it click; `example` a line of the model's own
  numbers (with their ids) for when the conversation gets there; `builds_on_concept` a
  concept of the same card to explain first. It is material, not a script: the agent
  takes what the question needs, in its own words and at its own pace.
- **`pypsa_example`** points at the toy model that shows the concept arising in an actual
  PyPSA optimisation, for "how does this relate to PyPSA?": `{model, why, figures}`, the
  model's slug, one sentence on what the experiment shows, and the figure ids of that model
  to show first. The index row carries `pypsa_example: <slug>` too.
- **Concepts** come from the vocabulary in `index.yaml`; add to the list when a new model
  needs a new tag.
- **Numbers** are defined in the card (id, label, unit, formula) and valued in
  `results.yaml`; `index.yaml` lists the ids worth quoting.

## The models

The first twelve are the core; the rest were added on 2026-09-24 to cover the remaining PyPSA example gallery.

| slug | question | builds on |
|---|---|---|
| merit-order-dispatch | why the price is the marginal cost of the last unit | |
| nodal-prices-lopf | how prices split by bus when a line binds | |
| unit-commitment | what start-up costs and minimum times do to dispatch and prices | merit-order-dispatch |
| storage-arbitrage | what a battery earns from the daily spread | merit-order-dispatch |
| capacity-expansion-single-node | the cheapest mix under a CO2 cap, and the CO2 price it implies | |
| screening-curves | the optimal thermal mix from cost lines and a load duration curve | |
| price-duration-and-cost-recovery | whether what the optimiser builds recovers its cost | capacity-expansion-single-node |
| redispatch | what a zonal market plus redispatch costs against nodal pricing | nodal-prices-lopf |
| stochastic-cvar | planning under an uncertain gas price, risk-neutral and CVaR | capacity-expansion-single-node |
| myopic-pathway | horizons in sequence with inherited builds and retirements | capacity-expansion-single-node |
| sector-coupling-single-node | heat and hydrogen on the electricity node | capacity-expansion-single-node |
| transmission-expansion | how much link to build to a wind region | capacity-expansion-single-node |
| rolling-horizon | what perfect foresight assumes and how much it flatters storage | storage-arbitrage |
| water-values | what a water value is and where it comes from in a model | rolling-horizon |
| security-constrained-lopf | what N-1 security means for dispatch and what it costs | nodal-prices-lopf |
| reserve-constraints | how to add a constraint PyPSA does not have built in | merit-order-dispatch |
| maintenance-scheduling | when a plant should schedule its outage | unit-commitment |
| line-loading-limits | how to give a line a time-varying rating | nodal-prices-lopf |
| mga-near-optimal | how robust the optimal capacity mix is and what else costs nearly the same | capacity-expansion-single-node |
| perfect-foresight-pathway | the difference between perfect-foresight and myopic pathway planning | myopic-pathway |
| modular-committable-expansion | what discrete plant sizes do to the optimal mix | capacity-expansion-single-node, unit-commitment, price-duration-and-cost-recovery |
| weather-year-uncertainty | how to put different weather years into one stochastic problem | capacity-expansion-single-node, stochastic-cvar |
| time-series-aggregation | how coarse the time resolution can be before the mix is wrong | capacity-expansion-single-node |
| spatial-clustering | what clustering to fewer buses does to prices and flows | nodal-prices-lopf |
| demand-elasticity | how to model price-elastic demand and what it does to the peak price | merit-order-dispatch |
| cfd-ppa-settlement | what a wind farm earns under a CfD versus the market and what the CfD costs | price-duration-and-cost-recovery, capacity-expansion-single-node |
| renewable-revenue-risk | why wind earns less, and less predictably, as wind and solar grow | capacity-expansion-single-node, price-duration-and-cost-recovery |
| flow-based-market-coupling | what flow-based market coupling is and how it differs from NTC | nodal-prices-lopf |
| imperfect-competition | how much a strategic generator withholds and what it does to the price | demand-elasticity |
| tracing-infeasibilities | how to find out why a PyPSA model is infeasible with HiGHS | unit-commitment |
| cost-sensitivity | which technology cost assumption matters most for the result | capacity-expansion-single-node |
| ev-charging-v2g | what uncontrolled EV charging does to the evening peak | storage-arbitrage |
| chp-heat-power | how to model backpressure and extraction CHP plants in PyPSA |  |
| hydro-cascade | how to chain reservoirs so the upper station feeds the lower one |  |
| carbon-management | how to track CO2 across capture, storage and fuel synthesis | capacity-expansion-single-node |
| islanded-methanol | what green methanol costs from a stand-alone wind and solar plant | capacity-expansion-single-node |

## Adding a model

Copy the closest directory, keep the `model.py` skeleton (the five functions and the
`sys.path` insert), build charts only through `_lib/charts.py`, write the card, add the
row to `index.yaml`, run it, then run both checks. Keep it under ten seconds of solve time
and under four buses; anything bigger belongs in a method or a topic, not here.
