#!/usr/bin/env python3
"""Build the machine-readable provenance index over ALL cookbooks.

Walks cookbooks/{pypsa-eur,pypsa-earth}/{topics,generation_conversion,demand,
data_quality}/*.yaml plus cookbooks/methods/*.yaml and extracts every
`provenance:` citation (the `file:symbol; file:symbol` convention) and every
v2 method `where:` anchor. Output: cookbooks/_qa/provenance_index.json —

    { "<model>": { "<file>": { "<symbol>": [ {"doc": ..., "at": ...}, ... ] } } }

`model` is the cookbook dir segment (pypsa-eur / pypsa-earth) or "shared" for
the methods book (checked against BOTH models by consumers). DERIVED artifact:
regenerate with this script, never hand-edit. Consumed by upstream_impact.py.

v2 TODO: negative-knowledge polarity — dead-key and absent-feature claims are
prose today; when they gain a machine-readable field, index them with
polarity="absent" so a key coming ALIVE upstream also flags.

Usage: python3 cookbooks/_qa/build_provenance_index.py [--out PATH]
"""

import argparse
import json
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
COOKBOOKS = HERE.parent
BOOK_DIRS = ("topics", "generation_conversion", "demand", "data_quality")
CITE_RE = re.compile(r"^\s*([\w./\-]+\.(?:py|yaml|smk|csv)|Snakefile)\s*:\s*(.+?)\s*$")


def walk_provenance(node, hits, where):
    """Recursively collect provenance strings + v2 `where:` anchors."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("provenance", "where") and isinstance(v, str):
                hits.append((v, f"{where}.{k}"))
            else:
                walk_provenance(v, hits, f"{where}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk_provenance(v, hits, f"{where}[{i}]")


def parse_citations(raw):
    """'a.py:sym; b.yaml:key' -> [(file, symbol), ...]; skips prose."""
    out = []
    for part in raw.split(";"):
        m = CITE_RE.match(part.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(HERE / "provenance_index.json"))
    args = ap.parse_args()

    index = {}   # model -> file -> symbol -> [locations]
    n_docs = n_cites = 0
    sources = []
    # v1 cards/essays live in a v1/ subdir of their book pending migration
    for model in ("pypsa-eur", "pypsa-earth"):
        for book in BOOK_DIRS:
            d = COOKBOOKS / model / book
            sources += [(model, p) for p in
                        sorted(d.glob("*.yaml")) + sorted(d.glob("v1/*.yaml"))]
    sources += [("shared", p) for p in
                sorted((COOKBOOKS / "methods").glob("*.yaml"))
                + sorted((COOKBOOKS / "methods").glob("v1/*.yaml"))]

    for model, path in sources:
        try:
            doc = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        n_docs += 1
        hits = []
        walk_provenance(doc, hits, "")
        rel = str(path.relative_to(COOKBOOKS))
        for raw, at in hits:
            for file, symbol in parse_citations(raw):
                index.setdefault(model, {}).setdefault(file, {}) \
                     .setdefault(symbol, []).append({"doc": rel, "at": at.lstrip(".")})
                n_cites += 1

    Path(args.out).write_text(json.dumps(
        {"generated_from": str(COOKBOOKS), "docs": n_docs,
         "citations": n_cites, "index": index}, indent=1))
    print(f"indexed {n_cites} citations from {n_docs} docs -> {args.out}")


if __name__ == "__main__":
    main()
