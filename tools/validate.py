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


def validate_topic_sections() -> list[str]:
    """Every topic's model section carries trade_offs[] and limitations[], no pitfalls."""
    import yaml

    errors: list[str] = []
    for path in sorted((ROOT / "topics").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        for sec in doc.get("models") or []:
            where = f"topic {path.stem}/{sec.get('model')}"
            if "pitfalls" in sec:
                errors.append(f"{where}: pitfalls was split into trade_offs and limitations")
            for key in ("trade_offs", "limitations"):
                value = sec.get(key)
                if not isinstance(value, list) or not all(
                    isinstance(p, str) and p.strip() for p in value
                ):
                    errors.append(f"{where}: {key} must be a list of strings")
    return errors


TOYMODELS = ROOT / "toymodels"
TOYMODEL_CARD_KEYS = {
    "id", "title", "summary", "concepts", "answers", "builds_on", "setup", "method",
    "knobs", "figures", "numbers", "limitations", "sources", "pypsa",
}
TOYMODEL_FORBIDDEN = {"models", "version_anchor", "schema_version"}


def validate_toymodels() -> list[str]:
    """`toymodels/`: index rows match directories, cards are complete, outputs are present.

    A toy model is `toymodels/<slug>/` with `card.yaml`, `model.py`, generated
    `results.yaml` and `figures/<id>.json` for every figure the card and the index name.
    Cards pin `pypsa:` and carry no `models:` or `version_anchor:` (plain PyPSA, not a
    workflow model). Concepts come from the vocabulary in `index.yaml`.
    """
    import json

    import yaml

    errors: list[str] = []
    index_path = TOYMODELS / "index.yaml"
    if not index_path.exists():
        return [f"{index_path.relative_to(ROOT)} missing"]
    index = yaml.safe_load(index_path.read_text())
    vocabulary = set(index.get("concepts_vocabulary") or [])
    rows = {row["id"]: row for row in index.get("models") or []}
    dirs = {p.name for p in TOYMODELS.iterdir() if p.is_dir() and not p.name.startswith("_")}
    for missing in sorted(dirs - set(rows)):
        errors.append(f"toymodels/{missing}: directory has no row in index.yaml")
    for missing in sorted(set(rows) - dirs):
        errors.append(f"toymodels index: {missing} has no directory")
    for slug in sorted(dirs & set(rows)):
        d = TOYMODELS / slug
        where = f"toymodels/{slug}"
        for name in ("card.yaml", "model.py", "results.yaml"):
            if not (d / name).exists():
                errors.append(f"{where}: {name} missing")
        if not (d / "card.yaml").exists():
            continue
        card = yaml.safe_load((d / "card.yaml").read_text())
        if card.get("id") != slug:
            errors.append(f"{where}: card id is {card.get('id')!r}")
        keys = set(card)
        for key in sorted(TOYMODEL_CARD_KEYS - keys):
            errors.append(f"{where}: card lacks {key}")
        for key in sorted(keys & TOYMODEL_FORBIDDEN):
            errors.append(f"{where}: card must not carry {key}")
        for key in sorted(keys - TOYMODEL_CARD_KEYS):
            errors.append(f"{where}: card has unknown key {key}")
        if not isinstance(card.get("pypsa"), str):
            errors.append(f"{where}: pypsa must be a version string")
        row = rows[slug]
        for tag in list(card.get("concepts") or []) + list(row.get("concepts") or []):
            if tag not in vocabulary:
                errors.append(f"{where}: concept {tag!r} not in the index vocabulary")
        if row.get("builds_on", []) != card.get("builds_on", []):
            errors.append(f"{where}: builds_on differs between card and index")
        for dep in card.get("builds_on") or []:
            if dep not in dirs:
                errors.append(f"{where}: builds_on {dep!r} is not a toy model")
        results = yaml.safe_load((d / "results.yaml").read_text()) if (d / "results.yaml").exists() else {}
        numbers = results.get("numbers") or {}
        # a number is either a top-level key or, for models whose numbers are grouped by
        # case (a cap, a link cost), a key inside every such group
        groups = [v for v in numbers.values() if isinstance(v, dict)]
        for key in row.get("numbers") or []:
            if key not in numbers and not any(key in g for g in groups):
                errors.append(f"{where}: index number {key!r} not in results.yaml")
        card_figs = {f["id"]: f for f in card.get("figures") or []}
        index_figs = {f["id"] for f in row.get("figures") or []}
        if set(card_figs) != index_figs:
            errors.append(f"{where}: figure ids differ between card and index")
        for fid, fig in card_figs.items():
            path = d / fig.get("file", f"figures/{fid}.json")
            if not path.exists():
                errors.append(f"{where}: {path.name} missing")
                continue
            try:
                doc = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                errors.append(f"{where}/{path.name}: not JSON ({exc})")
                continue
            if doc.get("version") != 1 or "option" not in doc or "datasets" not in doc:
                errors.append(f"{where}/{path.name}: not a version-1 figure bundle")
            elif "title" in doc["option"]:
                errors.append(f"{where}/{path.name}: option carries a title")
        meta_figs = set((results.get("meta") or {}).get("figures") or {})
        if meta_figs and meta_figs != set(card_figs):
            errors.append(f"{where}: results.yaml figures {sorted(meta_figs)} differ from the card")
    return errors


def main() -> int:
    r = load_restructure()
    r.ANCHORS["pypsa-eur"] = EUR_ANCHOR
    # CLAUDE.md, tools/ and toymodels/ postdate the frozen TOP_LEVEL set; baselines/
    # was removed on 2026-09-11 when the app dropped baseline runs.
    r.TOP_LEVEL |= {"CLAUDE.md", "tools", "toymodels"}
    r.TOP_LEVEL -= {"baselines"}
    errors: list[str] = []

    staged = subprocess.run(
        ["git", "ls-files", "-s", "models/pypsa-eur"], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()
    gitlink = staged[1] if len(staged) >= 2 else submodule_gitlink("models/pypsa-eur")
    if gitlink != EUR_ANCHOR:
        errors.append(f"models/pypsa-eur gitlink is {gitlink}, anchor is {EUR_ANCHOR}")

    topics, method_models, scan_errors = r.scan_disk()
    errors += scan_errors
    # The frozen validator predates the 2026-09-13 split of a topic section's
    # `pitfalls` into `trade_offs` and `limitations`; its one check on the old
    # key is dropped here and the live shape is checked below.
    errors += [e for e in r.validate(topics, method_models) if "pitfalls must be" not in e]
    errors += validate_topic_sections()
    errors += validate_toymodels()
    for e in errors:
        print("ERROR", e)
    print("ok" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
