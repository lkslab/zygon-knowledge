# -*- coding: utf-8 -*-
"""
Shared core for topics/INDEX.md generation. The two per-model entry points

    cookbooks/pypsa-eur/topics/_qa/generate_index.py
    cookbooks/pypsa-earth/topics/_qa/generate_index.py

are thin drivers over this module; before 2026-08-02 they were full duplicates
differing in one preamble string.
"""

import os

import yaml

import topic_card_lib

VERDICT_BADGE = {"ready": "ready", "partial": "partial", "gap": "GAP"}


def methods_cell(card, model, specs):
    """Linked method ids, `*`-marked where the spec is not yet verified here."""
    out = []
    for m in card.get("methods") or []:
        mid = m.get("id")
        path = specs.get(mid)
        mark = ""
        if path:
            _, status = topic_card_lib.method_status(path, model)
            mark = "" if status == "verified" else "*"
        out.append(f"`{mid}`{mark}")
    return ", ".join(out) or "—"


def generate(qa_dir, model):
    book_dir = os.path.dirname(qa_dir)
    specs = topic_card_lib.method_specs(topic_card_lib.locate(qa_dir)["methods_dir"])

    cards = []
    for sub in (".", "v1"):  # v1 cards live in v1/ pending migration
        d = os.path.join(book_dir, sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if f.endswith(".yaml") and f != "FUNCTIONALITY.yaml":
                card = yaml.safe_load(open(os.path.join(d, f)))
                card["_link"] = f if sub == "." else f"{sub}/{f}"
                cards.append(card)
    cards.sort(key=lambda d: d["rank"])

    registry = {d["id"]: d for d in
                yaml.safe_load(open(os.path.join(book_dir, "FUNCTIONALITY.yaml")))}

    counts = {"ready": 0, "partial": 0, "gap": 0}
    n_v2 = 0
    lines = [
        "# Topics cookbook — index",
        "",
        "One wiring card per planning/analysis topic (Appendix A of",
        "`energy_topics/energy_modelling_demand_landscape.md`, ranked by urgency).",
        "",
        "**`v` is the first thing to read.** A `2` card has been migrated: it links",
        "executable method specs (`methods:`, `*` = not yet verified on this model)",
        "and is usable to scope a study. A `1` card still wires to the capability",
        "registry (`FUNCTIONALITY.yaml`) and **cannot scope a study** — the topic is",
        "real, the wiring for it is not written yet. Say so and stop.",
        "",
        f"Coverage: **ready** = the standard {model} workflow answers it;",
        "**partial** = a meaningful slice works with config effort;",
        "**GAP** = core machinery missing (the card says what to build).",
        "",
        "| # | topic | v | coverage | recipes | methods | missing functionality |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in cards:
        counts[d["coverage"]] += 1
        sv = 2 if d.get("schema_version") == 2 else 1
        n_v2 += sv == 2
        n_rec = sum(len(v or []) for v in (d.get("recipes") or {}).values())
        gaps = [f["id"] for f in (d.get("functionality") or [])
                if registry.get(f["id"], {}).get("status") in ("absent", "dead-key")]
        lines.append(
            f"| {d['rank']} | [{d['title']}]({d['_link']}) | {sv} "
            f"| {VERDICT_BADGE[d['coverage']]} | {n_rec} "
            f"| {methods_cell(d, model, specs)} "
            f"| {', '.join(f'`{g}`' for g in gaps) or '—'} |")

    lines += [
        "",
        f"**Coverage: {counts['ready']} ready · {counts['partial']} partial · "
        f"{counts['gap']} gap** (of {len(cards)}). "
        f"**Migrated: {n_v2} v2 / {len(cards) - n_v2} v1.**",
        "",
    ]
    out = os.path.join(book_dir, "INDEX.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {out}: {len(cards)} cards "
          f"({counts['ready']} ready / {counts['partial']} partial / {counts['gap']} gap)")
