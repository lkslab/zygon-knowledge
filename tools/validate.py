#!/usr/bin/env python3
"""Validate the tree with the app's `knowledge` reader.

Opens each model's cards through `knowledge.Knowledge` and the policy tables through
`knowledge.Policy`, then runs the checks the reader skips (`checks.py`): canonical
anchors, cited-method closure, payload layout and the `models/<model>` gitlinks.
The reader comes from a pypsa-app checkout, found with `--app`, `$PYPSA_APP`, the
submodule layout or a sibling `pypsa-app/`:

    python3 tools/validate.py [--app <pypsa-app checkout>]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The eur ref is the fork commit the app pins (the `workflows/pypsa-eur` gitlink and the
# profile's `pinned_ref`); it must equal the `models/pypsa-eur` gitlink.
ANCHORS = {
    "pypsa-eur": "09e8910ae03ace9af8ff821514cda7822fdd473f",
    "pypsa-earth": "8435f4c8cc05f30088933b37b7db497ff860dc53",
}


def app_src(explicit: Path | None) -> Path:
    """The app's `src/` directory, which holds the `knowledge` package."""
    if explicit is not None:
        return explicit / "src"
    if os.environ.get("PYPSA_APP"):
        return Path(os.environ["PYPSA_APP"]) / "src"
    candidates = [ROOT.parents[2] / "src", ROOT.parent / "pypsa-app" / "src"]
    for candidate in candidates:
        if (candidate / "knowledge" / "cards.py").is_file():
            return candidate
    raise SystemExit("no pypsa-app checkout found; pass --app")


def submodule_gitlink(path: str) -> str | None:
    staged = subprocess.run(
        ["git", "ls-files", "-s", path], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    if len(staged) >= 2:
        return staged[1]
    tree = subprocess.run(
        ["git", "ls-tree", "HEAD", path], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    return tree[2] if len(tree) >= 3 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app", type=Path, help="pypsa-app checkout")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(app_src(args.app)))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import checks
    from knowledge import MODELS, TABLES, Knowledge, KnowledgeError, Policy

    errors: list[str] = []
    has_topics = (ROOT / "topics").is_dir()
    if not has_topics:
        errors.append("topics/ missing")
    for model in MODELS:
        handle = Knowledge.open(ROOT, model) if has_topics else None
        if handle is not None:
            readers = {
                "topics": handle.topics,
                "carriers": handle.carriers,
                "methods": handle.methods,
                "data quality cards": handle.data_quality_cards,
            }
            unreadable = False
            for kind, read in readers.items():
                try:
                    if not read():
                        errors.append(f"{model}: no {kind}")
                except KnowledgeError as exc:
                    unreadable = True
                    errors.append(str(exc))
            if not unreadable:
                errors += checks.anchor_errors(handle, ANCHORS[model])
                errors += checks.citation_errors(handle)
                errors += checks.identity_errors(handle)
        gitlink = submodule_gitlink(f"models/{model}")
        if gitlink != ANCHORS[model]:
            errors.append(f"models/{model} gitlink is {gitlink}, anchor is {ANCHORS[model]}")

    errors += checks.validate_payloads(ROOT)

    policy = Policy.open(ROOT)
    if policy is None:
        errors.append("policy/ missing")
    else:
        try:
            if set(policy.coverage("DE")) != set(TABLES):
                errors.append("policy coverage for DE does not span every table")
        except KnowledgeError as exc:
            errors.append(str(exc))

    for e in errors:
        print("ERROR", e)
    print("ok" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
