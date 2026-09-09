# Pass 2 — author ONE method card

You write exactly one file: `cookbooks/methods/<SLUG>.yaml`. Work from
`/home/lukas/Desktop/zygon`. You are one of ~35 agents, one per method.

## Read these first, in this order

1. `cookbooks/methods/_qa/METHOD.schema.yaml` — the contract. Every field, its shape,
   the rung legend, the four `available.verdict` values, the forbidden fields.
2. `cookbooks/methods/v1/mga-near-optimal-space.yaml` — the worked exemplar. **Match its
   depth, tone and level of grounding.** It is the house style: specific, cited,
   honest about what is missing, no filler.
3. Your evidence slice — the papers that use your method, already read by pass 1:
   ```
   python3 -c "
   import yaml; d=yaml.safe_load(open('cookbooks/methods/_qa/EVIDENCE.yaml'))
   s='<SLUG>'
   print(yaml.safe_dump(d['index'][s]))
   print(yaml.safe_dump(d['methods'][s], sort_keys=False, allow_unicode=True, width=100))"
   ```
4. `cookbooks/methods/_qa/SLUGS.yaml` — your `one_line` definition, your `family`, and
   the other 34 slugs (for `requires_methods` / `combines_with` — those MUST be slugs
   from this list).
5. `cookbooks/methods/_qa/FUNCTIONALITY.index.md` — the 119 capability ids with their
   per-model status. Pick the 5-8 your method rests on, then **grep the full registry**
   for their `surface:` and `consumer:` lines:
   `grep -A5 "id: <the-id>" cookbooks/pypsa-eur/topics/FUNCTIONALITY.yaml`
   (and the pypsa-earth one). Those give you the config keys and file:symbols to verify.

## Hard rules

**PAPERS: you may not open a PDF or a file under `_qa/text/`.** Pass 1 already read
them; your slice's `evidence` and `procedure_notes` are what you have. If the evidence
is too thin for a field, write the field honestly short and append a line to
`cookbooks/methods/_qa/GAPS.md` naming the slug, the field and what you would need.
Do not pad and do not infer a paper's method from its title.
*(One documented exception, `model-validation-and-backtesting`, is told so explicitly.)*

**MODELS: read-only.** Grep and read `models/pypsa-eur/` and `models/pypsa-earth/`
freely. Never edit anything in them.

**PROVENANCE: grep every symbol before you write it.** This is the whole point of the
book. `provenance` is `file:symbol`, paths relative to that model's repo root, and
**never a line number**. Verify each one:
```
grep -n "<symbol>" models/pypsa-eur/<file>          # must hit
python3 -c "import yaml;c=yaml.safe_load(open('models/pypsa-eur/config/config.default.yaml'));
            n=c
            for k in '<dotted.key>'.split('.'): n=n[k]
            print(repr(n))"                          # levers[].key must resolve, and gives you `default`
```
pypsa-earth's config is at `models/pypsa-earth/config.default.yaml` (no `config/` dir).
A `pypsa_primitive.symbol` is relative to site-packages in
`/home/lukas/Desktop/earth/pypsa-earth/.pixi/envs/default/lib/python3.11/site-packages`
(pypsa 0.30.3) — e.g. `pypsa/optimization/abstract.py:optimize_security_constrained`.
Set `pypsa_primitive: null` if there genuinely is no library primitive.

**BOTH model sections are required**, `pypsa-eur` first then `pypsa-earth`. Use
`not_applicable: <reason>` rather than omitting one. Version anchors:
- pypsa-eur: `849c8858d2536ccf8eed0c2e838d22a474a7ee5d`
- pypsa-earth: `8435f4c8cc05f30088933b37b7db497ff860dc53`
- date: `2026-07-25`

## What makes a card good rather than merely valid

- **`procedure` is the centre of gravity.** Numbered steps as the literature actually
  performs them, with `handle` naming the callable/config that does each step, or
  `null` when there is none. `handle: null` steps ARE the L5 work — that is how the
  card summarises itself. `handle` and `provenance` must be null together.
- **`available.verdict` is what an interview reads first.** Be strict:
  `turnkey` = a config flip runs the method · `assemble` = every surface exists, you
  wire them (then `assembly` is mandatory and is the most valuable field you write) ·
  `primitive-only` = pypsa has it, no workflow config reaches it ·
  `absent` = neither layer has it.
- **The eur/earth asymmetry is the payload.** Where the models differ, say so
  concretely (eur has `perfect-foresight` working and earth has no registry entry at
  all; earth has a Monte-Carlo harness eur lacks; earth's blocker is usually data, not
  code). A card whose two model sections read identically is a card that did not look.
- **`boundary` rungs must be defensible from the registry status and your greps.** If
  the registry says `working` and a config key exists, it is L0/L1 — do not inflate to
  L5 for drama. If the registry says `absent`, do not deflate to L1 because a
  vaguely-related key exists.
- **`pitfalls` is where `critiques`-role papers land.** How the method misleads you when
  it *does* run — distinct from `available.missing`, which is what you cannot run.
- **`prevalence`** — `papers` MUST equal `len(literature)` and `tier1 + tier2` MUST
  equal `papers` (the checker does this arithmetic). Put the count from your slice's
  `index` block in, and in `basis` state the hand-coded count, the `sweep_hits` from
  `grep '<SLUG>' cookbooks/methods/_qa/SWEEP.csv | wc -l`, and why they differ if they
  do. **Exclude mention-only claims** — check
  `cookbooks/methods/_qa/EVIDENCE_INDEX.md` for flagged suspects in your slice and
  judge each one; a paper that only names your method is not in your `literature`.
- **`variants[].id` and `boundary[].variant` must join both ways.** Every variant needs
  a rung on at least one model.
- Mine `EVIDENCE.yaml:unmatched_methods` for one-off techniques related to your method —
  several are `variants` or `procedure` detail that pass 1 had no slug for.

## Before you finish

```
python3 cookbooks/methods/_qa/check_methods.py --only <SLUG>
```
**It must exit 0.** Fix every error yourself; do not report a failing card as done. If
the checker rejects a claim you believe is true, the claim is probably subtly wrong (a
symbol that is a prefix of the real one, a config key one level off) — re-grep it.

## Your reply to the orchestrator

**Two lines maximum**: the card path, `check_methods.py` result, the two
`available.verdict` values (eur/earth), and the entry-level rung. Then, only if
relevant, one clause on anything surprising you found. No summary of the method.
Example: `wrote mga-near-optimal-space.yaml — checker ok — eur primitive-only / earth
primitive-only, entry L5; earth's monte_carlo.py is a reusable many-solve harness eur lacks.`
