#!/usr/bin/env python3
"""Schema check for the live tree, with the current pypsa-eur anchor.

`archive/tools/restructure.py --validate` is the schema validator, but `archive/` is
frozen and its `ANCHORS` constant still names the pre-2026-09 fork anchor. This wrapper
imports that module unchanged, overrides the pypsa-eur anchor with the sha the
`models/pypsa-eur` submodule is pinned to, and runs the same `scan_disk` + `validate`
pass. Run from anywhere:

    python3 tools/validate.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Canonical pypsa-eur anchor: upstream master, "Streamline workflow" (#1838), 2026-09-09.
# Must equal the models/pypsa-eur gitlink; checked below.
EUR_ANCHOR = "a6c45e5a2d926ba9a5566cba24d905cff9f89939"


def load_restructure():
    path = ROOT / "archive" / "tools" / "restructure.py"
    spec = importlib.util.spec_from_file_location("restructure", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def submodule_gitlink(path: str) -> str | None:
    out = subprocess.run(
        ["git", "ls-tree", "HEAD", path], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    return out[2] if len(out) >= 3 else None


def main() -> int:
    r = load_restructure()
    r.ANCHORS["pypsa-eur"] = EUR_ANCHOR
    # CLAUDE.md and tools/ postdate the frozen TOP_LEVEL set.
    r.TOP_LEVEL |= {"CLAUDE.md", "tools"}
    errors: list[str] = []

    staged = subprocess.run(
        ["git", "ls-files", "-s", "models/pypsa-eur"], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    gitlink = staged[1] if len(staged) >= 2 else submodule_gitlink("models/pypsa-eur")
    if gitlink != EUR_ANCHOR:
        errors.append(f"models/pypsa-eur gitlink is {gitlink}, anchor is {EUR_ANCHOR}")

    topics, method_models, scan_errors = r.scan_disk()
    errors += scan_errors
    errors += r.validate(topics, method_models)
    for e in errors:
        print("ERROR", e)
    print("ok" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
