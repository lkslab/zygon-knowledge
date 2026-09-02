#!/usr/bin/env python3
"""Upstream-impact scout — the mechanical first pass of every epoch bump.

Given a candidate upstream ref for a model submodule, answers: which cookbook
claims does moving there break, and which recipes/cards/methods need
re-authoring? Pure git + grep, no LLM: the semantic pass (an agent drafting
the actual adjustments from the diff hunks) runs AFTER this, on the BROKEN
list only.

Buckets per cited (file, symbol):
  UNTOUCHED  cited file unchanged between refs           (not listed)
  INTACT     file changed but the symbol still greps     (low-priority eyes)
  BROKEN     symbol gone at the candidate ref, or the file deleted/renamed
             -> the ranked re-authoring worklist, grouped by cookbook doc

Usage (from the zygon repo root):
  python3 cookbooks/_qa/build_provenance_index.py          # refresh the index
  python3 cookbooks/_qa/upstream_impact.py --model pypsa-eur --to <ref> \
      [--from-ref HEAD] [--json out.json]

`--to` must be fetchable in models/<model> (fetch the remote first for a
pre-bump drift report). Exit 0 = no BROKEN citations, 1 = some, 2 = usage.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZYGON = HERE.parent.parent
INDEX = HERE / "provenance_index.json"


def git(model_dir, *args):
    p = subprocess.run(["git", "-C", str(model_dir)] + list(args),
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"git {' '.join(args[:2])} failed: {p.stderr.strip()[:200]}")
    return p.stdout


def show(model_dir, ref, path):
    p = subprocess.run(["git", "-C", str(model_dir), "show", f"{ref}:{path}"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", required=True,
                    choices=["pypsa-eur", "pypsa-earth"])
    ap.add_argument("--to", required=True, help="candidate upstream ref")
    ap.add_argument("--from-ref", default="HEAD",
                    help="current anchor (default: submodule HEAD)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if not INDEX.is_file():
        sys.exit("no provenance_index.json — run build_provenance_index.py first")
    idx = json.loads(INDEX.read_text())["index"]
    model_dir = ZYGON / "models" / args.model

    changed = set(git(model_dir, "diff", "--name-only",
                      f"{args.from_ref}..{args.to}").splitlines())
    # citations for this model + the shared methods book
    cites = {}
    for scope in (args.model, "shared"):
        for file, symbols in (idx.get(scope) or {}).items():
            for symbol, locs in symbols.items():
                cites.setdefault((file, symbol), []).extend(locs)

    intact, broken = [], []
    for (file, symbol), locs in sorted(cites.items()):
        if file not in changed:
            continue
        content = show(model_dir, args.to, file)
        entry = {"file": file, "symbol": symbol,
                 "docs": sorted({l["doc"] for l in locs})}
        if content is None:
            entry["why"] = "file deleted/renamed at candidate ref"
            broken.append(entry)
        elif symbol not in content:
            entry["why"] = "symbol no longer greps at candidate ref"
            broken.append(entry)
        else:
            intact.append(entry)

    by_doc = {}
    for e in broken:
        for d in e["docs"]:
            by_doc.setdefault(d, []).append(f"{e['file']}:{e['symbol']}")

    print(f"# upstream impact — {args.model} {args.from_ref}..{args.to}")
    print(f"changed files: {len(changed)} | citations touched: "
          f"{len(intact) + len(broken)} | INTACT {len(intact)} | "
          f"BROKEN {len(broken)}\n")
    if broken:
        print("## BROKEN — the re-authoring worklist, by cookbook doc\n")
        for doc, refs in sorted(by_doc.items(), key=lambda kv: -len(kv[1])):
            print(f"- {doc}  ({len(refs)} broken)")
            for r in refs:
                print(f"    {r}")
    if intact:
        print(f"\n## INTACT but file changed — worth eyes ({len(intact)})\n")
        for e in intact:
            print(f"- {e['file']}:{e['symbol']}  <- {', '.join(e['docs'])}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"model": args.model, "from": args.from_ref, "to": args.to,
             "broken": broken, "intact": intact}, indent=1))
    sys.exit(1 if broken else 0)


if __name__ == "__main__":
    main()
