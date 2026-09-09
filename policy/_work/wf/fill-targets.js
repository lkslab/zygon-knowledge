export const meta = {
  name: 'brockhaus-fill-targets',
  description: 'Research national energy/climate targets for countries below the brockhaus floor and emit validated bundle JSONs',
  phases: [
    { title: 'Research', detail: 'one read-only agent per country, verbatim figures only' },
    { title: 'Audit', detail: 'adversarial check that each cited number is real' },
  ],
}

const BASE = '/home/lukas/Desktop/zygon/data/energy_brockhaus'

// Hardcoded rather than read from `args`: the previous run was handed the array
// but fell through to the single-country default, so the list lives here where
// it is unambiguous.
const COUNTRIES = ['SS', 'IL', 'VE', 'MW', 'ML', 'GE', 'ET', 'BO']

const BUNDLE_SCHEMA = {
  type: 'object',
  required: ['country', 'written', 'rows_emitted', 'sources_used', 'shortfall_reason'],
  properties: {
    country: { type: 'string' },
    written: { type: 'boolean' },
    rows_emitted: { type: 'integer' },
    sources_used: { type: 'array', items: { type: 'string' } },
    shortfall_reason: { type: 'string' },
  },
}

const AUDIT_SCHEMA = {
  type: 'object',
  required: ['country', 'checked', 'bad_rows', 'verdict'],
  properties: {
    country: { type: 'string' },
    checked: { type: 'integer' },
    bad_rows: {
      type: 'array',
      items: {
        type: 'object',
        required: ['record_id', 'problem'],
        properties: { record_id: { type: 'string' }, problem: { type: 'string' } },
      },
    },
    verdict: { type: 'string', enum: ['clean', 'suspect', 'reject'] },
  },
}

function researchPrompt(cc) {
  return `You are filling a gap in a global energy-policy registry at ${BASE}.

TASK: research national energy and climate TARGETS for ISO-2 country "${cc}" and
write a bundle JSON to ${BASE}/_work/bundles/${cc}.json

=== THE ONE RULE THAT MATTERS ===
Record ONLY numbers that appear VERBATIM in the source document.

A previous run failed audit on exactly two things. Do not repeat them:
  - It summed a table of individual power stations and recorded the total as if
    the document stated it. IT DID NOT. Never add, subtract, convert, average or
    otherwise derive a figure. If the document does not print the number you
    want to record, you do not have that number.
  - It invented baseline_year=2018 for an emissions target whose document never
    names a base year, and where the document gave both 31% and 44% for the same
    reduction it silently recorded the more flattering 44%.

Therefore:
  1. NEVER derive. Only transcribe. Unit conversion is derivation (do not turn
     MW into GW). Record the unit the document uses, provided it is in the
     allowed list below; if it is not, skip the row.
  2. baseline_year is filled ONLY if the document explicitly names the base year
     ("compared to 1990 levels"). Otherwise leave it "". A target measured
     against a projected business-as-usual trajectory is NOT basis
     "baseline_year" -- use basis "" and say so in scope_note.
  3. If the document states two different figures for the same thing, record the
     MORE CONSERVATIVE one, set confidence to "med" at most, and describe the
     conflict in notes. Never silently pick the better number.
  4. EVERY row's notes MUST begin with the verbatim sentence from the source that
     contains the figure, in double quotes. If you cannot quote a sentence
     containing that exact number, DELETE THE ROW. This is the check; treat it
     as the point of the exercise, not paperwork.
  5. confidence "high" requires: figure quoted verbatim, from a tier-1 document,
     with no internal conflict. Anything else is "med" or "low".
  6. Conditional and unconditional NDC targets are two different rows. Never
     merge them, and say which is which in scope_note.

You are graded ONLY on correctness. Emitting 2 solid rows beats 8 shaky ones.
Emitting 0 rows with an honest shortfall_reason beats 1 invented row.

=== STEP 1: what already exists (do not duplicate) ===
  cd ${BASE} && python3 tools/worklist.py show --country ${cc}
  python3 tools/registry.py query --country ${cc} --type targets --json
The "deficit" field says how many rows are still wanted. It is a target for
effort, NOT a quota. Do not pad to reach it.

=== STEP 2: research ===
Load web tools first: ToolSearch with query "select:WebSearch,WebFetch".
  tier 1: UNFCCC NDC Registry (https://unfccc.int/NDCREG) -- START HERE, every
          party has one. Then national ministry/gazette sites (.gov/.gouv/.gob/
          .go/.govt domains).
  tier 2: IEA, IRENA, Ember, World Bank, Climate Action Tracker,
          climate-laws.org.
  tier 3: press/wiki -- never "high", never the sole basis for a headline number.
Prefer a headline target the document states plainly over a detailed one you
would have to assemble.

=== STEP 3: write ${BASE}/_work/bundles/${cc}.json ===
Shape: {"targets": [ {row}, {row} ]}

Row keys, all required:
  record_id      "${cc}-T-<SLUG>-<YEAR>"
  country        "${cc}"
  technology     ALL allam ammonia battery biomass ccs clean_cooking coal
                 coal_ccs dac efuel_ft efuel_methane electricity energy_access
                 fossil gas gas_ccs geothermal_enhanced heat heat_pump hydro
                 hydrogen methanol nuclear other other_clean other_fossil
                 other_renewable renewables solar storage wind wind_offshore
                 wind_offshore_float wind_onshore
  metric         capacity co2_stored demand demand_buildings demand_industry
                 demand_other demand_total demand_transport emissions generation
                 mandate net_imports production removal share storage
                 storage_power
  value          bare number, no units, no commas, no thousands separators
  unit           EXACTLY one of: GW MW GWh MWh TWh PJ TWh/yr PJ/yr MtCO2eq MtCO2
                 MtCO2/yr pct Mt/yr kt/yr t/yr bcm/yr Smc/h Ggal/yr kb/d bbl/d
                 count ratio        <- "pct" not "%". No free text, ever.
  basis          "" gross_final_energy electricity_generation
                 electricity_consumption primary_energy installed_capacity
                 baseline_year present_level transport_energy fuel_volume
                 jet_fuel_demand gas_supply population households ghg_intensity
                 vehicle_sales heat_supply
  scope_note     qualifier or "" -- e.g. "conditional on international finance"
  year           target year
  baseline_year  only if the document names it explicitly, else ""
  scenario       legislated binding adopted ndc announced planned lts proposed
                 indicative
  binding        "binding" or "indicative"
  instrument_name  the plan or law
  source         short label of the document
  source_url     the exact URL you fetched
  retrieved      "2026-07-25"
  confidence     high | med | low
  last_updated   "2026-07-25"
  notes          MUST START with the verbatim quoted sentence containing the
                 figure, then any caveat.

=== STEP 4: validate, then self-audit ===
  cd ${BASE} && python3 tools/integrate_research.py _work/bundles/${cc}.json --dry-run
Fix rejections and re-run until it reports 0. Do NOT run it without --dry-run;
a separate serial step lands the data.

Then re-read your own file and delete any row where you cannot point at the
quote in notes and see the exact value. Report the final count honestly.`
}

function auditPrompt(cc, res) {
  return `Adversarially audit ${BASE}/_work/bundles/${cc}.json.

The producing agent reported ${res?.rows_emitted ?? 0} rows from:
${JSON.stringify(res?.sources_used ?? [])}

Your job is to REFUTE. Assume the agent padded to hit a quota until proven
otherwise. If the file does not exist, return checked=0, verdict "clean",
bad_rows [].

Load web tools: ToolSearch "select:WebFetch,WebSearch". For each row:
  1. notes must OPEN with a verbatim quoted sentence. Fetch source_url and
     confirm that sentence EXISTS in the document, word for word. A paraphrase
     is a fail.
  2. The quoted sentence must contain the recorded value. If the value was
     summed, converted or inferred from a table rather than printed, FAIL it --
     this is the specific failure mode that sank the previous run.
  3. Search the document for OTHER figures for the same target. If it states a
     lower or conflicting number that was not recorded, FAIL the row.
  4. baseline_year: if non-empty, the document must name that base year
     explicitly. An unstated or business-as-usual baseline is a FAIL.
  5. confidence "high" on a press/wiki source, or on any figure with an internal
     conflict, is a FAIL.
  6. Is it a forward TARGET, not a historical statistic or current installed
     capacity? Is a conditional NDC target flagged as conditional?

verdict "clean" only if EVERY row survives all six. "suspect" if any row fails.
"reject" if the document does not support the bundle at all.`
}

log(`filling targets for ${COUNTRIES.length} countries: ${COUNTRIES.join(', ')}`)

const results = await pipeline(
  COUNTRIES,
  (cc) => agent(researchPrompt(cc), {
    label: `research:${cc}`, phase: 'Research', schema: BUNDLE_SCHEMA,
  }),
  (res, cc) => agent(auditPrompt(cc, res), {
    label: `audit:${cc}`, phase: 'Audit', schema: AUDIT_SCHEMA,
  }).then((audit) => ({ cc, res, audit })),
)

const ok = results.filter(Boolean)
const clean = ok.filter((r) => r.audit?.verdict === 'clean' && (r.res?.rows_emitted ?? 0) > 0)
const flagged = ok.filter((r) => r.audit?.verdict !== 'clean')
const empty = ok.filter((r) => (r.res?.rows_emitted ?? 0) === 0)

return {
  clean: clean.map((r) => ({ cc: r.cc, rows: r.res.rows_emitted })),
  flagged: flagged.map((r) => ({
    cc: r.cc,
    verdict: r.audit?.verdict,
    bad_count: (r.audit?.bad_rows ?? []).length,
    bad: (r.audit?.bad_rows ?? []).slice(0, 3),
  })),
  no_data: empty.map((r) => ({ cc: r.cc, why: r.res?.shortfall_reason ?? 'nothing returned' })),
  totals: {
    countries: ok.length,
    rows_emitted: ok.reduce((n, r) => n + (r.res?.rows_emitted ?? 0), 0),
    clean_countries: clean.length,
  },
}
