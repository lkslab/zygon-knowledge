# Pass 1 — extract the methods used by ONE paper

You are extracting **method evidence** from exactly one research paper into one YAML
file. You are one of 100 agents doing this, one per paper. Your output is machine
input for a later synthesis step — not prose for a human.

## Your inputs

- The paper's extracted text: `cookbooks/methods/_qa/text/<STEM>.txt`
  (already extracted; read it with the Read tool. Papers are long — read the whole
  file if it is under ~2000 lines, otherwise read the abstract/intro, then the
  methods/model-description section, then skim results for method statements.
  **Methods are often in an appendix or SI at the end — check the tail of the file.**)
- The fixed method vocabulary: `cookbooks/methods/_qa/SLUGS.yaml` (34 slugs with
  one-line definitions). **You must use these slugs.** Do not invent slugs; the
  escape hatch is `unmatched_methods` (below).
- Screening hints for your paper: `grep '<PAPER FILENAME>' cookbooks/methods/_qa/SWEEP.csv`
  gives `paper,tier,slug,hits` from a regex screen. Hints are NOISY — a high hit
  count can be one word repeated in a literature review, and a real method can have
  zero hits. **Confirm or reject every hint by reading; add methods the screen missed.**

## Your output — exactly one file

Write `cookbooks/methods/_qa/paper_methods/<STEM>.yaml`:

```yaml
paper: "2020_Neumann_Near-Optimal-Feasible-Space_EPSR.pdf"   # exact filename with .pdf
tier: 1                                                       # 1 or 2, given to you
model_used: >
  Which model the paper actually runs: PyPSA-Eur | PyPSA-Eur-Sec | PyPSA-Earth |
  PyPSA-DE | PyPSA-GB | PyPSA-Spain | a bespoke PyPSA model | PyPSA library only |
  no model (review/tooling paper). Add the variant/resolution in a few words if the
  paper states it (e.g. "PyPSA-Eur, 181 nodes, electricity-only, 3h").
scope: >
  One line: what the paper studies. Enough for a synthesis agent to judge whether a
  method claim from this paper generalises.
methods:
  - slug: mga-near-optimal-space          # MUST be from SLUGS.yaml
    role: defines                          # defines | extends | canonical-use | routine-use | critiques
    evidence: >
      A short quote or close paraphrase (1-3 sentences) plus where it came from
      ("Sec. 2.2 Methods", "Eq. 4", "SI Sec. B"). THIS IS THE LOAD-BEARING FIELD:
      pass 2 may not open your paper, so anything not captured here is lost.
    procedure_notes: >
      What the paper says about HOW: the algorithm, what was held fixed, how many
      runs, what was swept, how results were post-processed. Be concrete.
    variant: broad-ranges                  # a short kebab-case name for the flavour used, or null
    parameters: {slack: "0.5%-10%", directions: "carrier-aligned + random"}
      # any numbers the paper states for this method: epsilon, resolution, node count,
      # horizon years, number of samples, discount rate. {} if none stated.
unmatched_methods:                          # the escape hatch — how the vocabulary grows
  - name: "short descriptive name"
    evidence: "quote + section, and why no existing slug fits"
```

## Rules

1. **`role` is about this paper's contribution to that method**, not the paper's
   importance. Most entries are `routine-use` — a paper that just runs a myopic
   pathway is `routine-use` for `foresight-and-planning-horizons`. Reserve
   `defines`/`extends` for genuine method content, and use `critiques` for a paper
   whose point is that the method misleads (e.g. clustering distorts, sensitivity
   swamps the result).
2. **Only list a method the paper actually USES or ANALYSES.** A method named once
   in the related-work section is not evidence. Omit it. Being complete about what a
   paper does matters less than never claiming something it does not do.
   **The failure mode to avoid, observed in practice:** logging an entry whose own
   `procedure_notes` then say "mentioned as motivation only", "named in the
   introduction", "not implemented in this paper", "listed as context" or "not
   exercised in the benchmark". If that is what you would write, **delete the entry**
   — a mention is not a use. Before you write the file, re-read each entry and apply
   this test: *did the authors run it, build it, or analyse its effect?* If no, drop it.
   A method the paper's own model configuration implies (it ran a single target year,
   so `foresight-and-planning-horizons` variant overnight) DOES count as
   `routine-use`, because the paper made that choice — cite where it states it.
3. **Do NOT speculate about config keys, rule names or scripts.** Model grounding
   happens in a later pass against the actual repos. If the paper names a config key
   or a fork, put it in `procedure_notes` as a quote, attributed to the paper.
4. **Do not edit anything except your one output file.** Do not touch `models/`,
   other agents' files, or the shared `_qa` artifacts.
5. Expect 3–10 methods per paper. A paper with 1 is suspicious (almost every study
   here makes a temporal, spatial and foresight choice); a paper with 20 means you
   are logging mentions rather than uses.
6. If the text is garbled or truncated (bad PDF extraction), write the file with
   `methods: []` and one `unmatched_methods` entry explaining the extraction problem.
   Do not guess from the title.

## Your reply to the orchestrator

**One line only**: the path you wrote, the count of methods, and any slug you had to
put in `unmatched_methods`. Nothing else — no summary of the paper, no reasoning.
Example: `wrote _qa/paper_methods/2020_Neumann_....yaml — 7 methods, 1 unmatched (polytope-vertex-enumeration)`
