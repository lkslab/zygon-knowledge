# -*- coding: utf-8 -*-
"""
The pivot between pass 1 and pass 2 of the methods book pipeline.

Pass 1 produced one record per PAPER (100 files in _qa/paper_methods/). Pass 2
writes one card per METHOD. This script inverts the first into the second so that
each card-authoring agent reads only its own slice — that inversion is what keeps
100 papers x 34 methods from becoming 3400 readings.

Outputs
  _qa/EVIDENCE.yaml     method slug -> [paper records citing it], plus an index
                        block with counts. Pass-2 agents read ONE slice of this.
  _qa/EVIDENCE_INDEX.md the reconcile view for pass 1.5: counts per method, the
                        union of unmatched_methods, and the mention-only suspects.

Also validates pass 1's output, because a malformed record is cheaper to catch here
than inside a card:
  - every CORPUS.yaml paper has exactly one record (no missing, no orphan)
  - every methods[].slug is in SLUGS.yaml
  - roles are in the enum; tier matches CORPUS.yaml
  - flags MENTION-ONLY SUSPECTS: entries whose procedure_notes admit the paper did
    not actually exercise the method. Pass-1 agents were told to drop these; the
    ones that slipped through would silently inflate prevalence, so they are
    reported for pass-1.5 review rather than trusted.

Usage:  python cookbooks/methods/_qa/pivot_evidence.py
Exit 0 iff pass-1 output is structurally sound (suspects are warnings, not errors).
"""

import os
import re
import sys
from collections import Counter, defaultdict

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
PM_DIR = os.path.join(QA_DIR, "paper_methods")

ROLES = {"defines", "extends", "canonical-use", "routine-use", "critiques"}

# Phrases that mean "the paper mentioned this, it did not do it". Pass-1
# instructions name these as the failure mode to avoid; this is the safety net.
MENTION_ONLY_RE = re.compile(
    r"mentioned (as|only|in)|named (as|in|only)|not (explicitly )?(implemented|exercised|"
    r"performed|applied|used|benchmarked|modelled|modeled)|motivation only|"
    r"as context, not|listed as context|no .{0,30}(comparison|analysis) is performed|"
    r"context, not a method|not a method the paper",
    re.IGNORECASE,
)


def load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    slugdoc = load(os.path.join(QA_DIR, "SLUGS.yaml"))
    slugs = [m["id"] for m in slugdoc["methods"]]
    slugset = set(slugs)
    corpus = load(os.path.join(QA_DIR, "CORPUS.yaml"))

    errors, suspects = [], []
    by_method = defaultdict(list)
    unmatched = defaultdict(list)
    seen_papers = set()

    files = sorted(f for f in os.listdir(PM_DIR) if f.endswith(".yaml"))
    for fname in files:
        path = os.path.join(PM_DIR, fname)
        try:
            doc = load(path)
        except yaml.YAMLError as e:
            errors.append(f"{fname}: YAML parse error: {e}")
            continue
        if not isinstance(doc, dict) or "paper" not in doc:
            errors.append(f"{fname}: missing top-level 'paper'")
            continue
        paper = doc["paper"]
        seen_papers.add(paper)
        if paper not in corpus:
            errors.append(f"{fname}: paper {paper!r} not in CORPUS.yaml")
            continue
        if doc.get("tier") != corpus[paper]["tier"]:
            errors.append(
                f"{fname}: tier {doc.get('tier')!r} != CORPUS tier {corpus[paper]['tier']}"
            )

        for i, m in enumerate(doc.get("methods") or []):
            slug = m.get("slug")
            if slug not in slugset:
                errors.append(f"{fname}: methods[{i}].slug not in SLUGS.yaml: {slug!r}")
                continue
            role = m.get("role")
            if role not in ROLES:
                errors.append(f"{fname}: methods[{i}].role invalid: {role!r}")
            notes = str(m.get("procedure_notes") or "")
            evid = str(m.get("evidence") or "")
            if MENTION_ONLY_RE.search(notes) or MENTION_ONLY_RE.search(evid):
                suspects.append((slug, paper, notes.strip().replace("\n", " ")[:160]))
            by_method[slug].append(
                {
                    "paper": paper,
                    "tier": doc["tier"],
                    "role": role,
                    "model_used": doc.get("model_used"),
                    "scope": doc.get("scope"),
                    "evidence": m.get("evidence"),
                    "procedure_notes": m.get("procedure_notes"),
                    "variant": m.get("variant"),
                    "parameters": m.get("parameters") or {},
                }
            )
        for u in doc.get("unmatched_methods") or []:
            name = str(u.get("name", "")).strip()
            if name:
                unmatched[name.lower()].append({"paper": paper, "evidence": u.get("evidence")})

    missing = sorted(set(corpus) - seen_papers)
    for p in missing:
        errors.append(f"no paper_methods record for {p}")

    # ---- EVIDENCE.yaml: the per-method slices pass 2 reads ------------------
    out = {
        "index": {
            slug: {
                "papers": len(by_method.get(slug, [])),
                "tier1": sum(1 for r in by_method.get(slug, []) if r["tier"] == 1),
                "tier2": sum(1 for r in by_method.get(slug, []) if r["tier"] == 2),
                "roles": dict(Counter(r["role"] for r in by_method.get(slug, []))),
            }
            for slug in slugs
        },
        "methods": {slug: by_method.get(slug, []) for slug in slugs},
        "unmatched_methods": {k: v for k, v in sorted(unmatched.items())},
    }
    with open(os.path.join(QA_DIR, "EVIDENCE.yaml"), "w") as f:
        f.write("# GENERATED by pivot_evidence.py from _qa/paper_methods/ — do not edit.\n")
        f.write("# Pass-2 agents read ONE slice: methods[<their slug>].\n")
        yaml.safe_dump(out, f, sort_keys=False, default_flow_style=False,
                       allow_unicode=True, width=100)

    # ---- EVIDENCE_INDEX.md: the pass-1.5 reconcile view --------------------
    lines = [
        "# Evidence index — the pass 1.5 reconcile view",
        "",
        "GENERATED by `pivot_evidence.py`. This is the gate that freezes the slug list:",
        "add recurring `unmatched`, merge slugs with the same paper set AND the same",
        "procedure, drop slugs with <2 papers and no distinct procedure.",
        "",
        f"{len(seen_papers)} papers, {sum(len(v) for v in by_method.values())} paper x method claims.",
        "",
        "## Prevalence per method (hand-coded pass 1)",
        "",
        "| method | papers | tier1 | tier2 | defines | extends | canonical | routine | critiques |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for slug in sorted(slugs, key=lambda s: -len(by_method.get(s, []))):
        rs = by_method.get(slug, [])
        c = Counter(r["role"] for r in rs)
        lines.append(
            f"| {slug} | {len(rs)} | {sum(1 for r in rs if r['tier']==1)} | "
            f"{sum(1 for r in rs if r['tier']==2)} | {c['defines']} | {c['extends']} | "
            f"{c['canonical-use']} | {c['routine-use']} | {c['critiques']} |"
        )

    lines += ["", "## Unmatched methods (candidates for new slugs / variants)", ""]
    for name, recs in sorted(unmatched.items(), key=lambda kv: -len(kv[1])):
        papers = ", ".join(os.path.splitext(r["paper"])[0][:38] for r in recs)
        lines.append(f"- **{name}** ({len(recs)}x) — {papers}")

    lines += [
        "",
        "## Mention-only suspects (review, likely delete)",
        "",
        "Entries whose own evidence/procedure_notes admit the paper did not exercise the",
        "method. Left in EVIDENCE.yaml but flagged: pass-2 authors must not count these",
        "in `prevalence`, and pass 1.5 should decide whether to strike them.",
        "",
    ]
    for slug, paper, note in sorted(suspects):
        lines.append(f"- `{slug}` / {os.path.splitext(paper)[0][:48]} — {note}")

    with open(os.path.join(QA_DIR, "EVIDENCE_INDEX.md"), "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"{len(seen_papers)}/{len(corpus)} papers pivoted; "
          f"{sum(len(v) for v in by_method.values())} claims across {len(by_method)} methods")
    print(f"{len(unmatched)} distinct unmatched method names")
    print(f"{len(suspects)} mention-only suspects flagged for pass-1.5 review")
    if errors:
        print(f"\n{len(errors)} STRUCTURAL ERRORS in pass-1 output:")
        for e in errors:
            print(f"  - {e}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
