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
import posixpath
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Canonical pypsa-eur anchor: upstream master, "Streamline workflow" (#1838), 2026-09-09.
# Must equal the models/pypsa-eur gitlink; checked below.
EUR_ANCHOR = "d2e0d48666f09a580c744846cef37e5059761d7a"


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
TOYMODEL_OPTIONAL = {"teach", "pypsa_example"}
TOYMODEL_FORBIDDEN = {"models", "version_anchor", "schema_version"}
TEACH_KEYS = {"concept", "gap", "remedy", "figure"}
TEACH_OPTIONAL = {"example", "builds_on_concept"}


def _check_teach(where: str, card: dict, figure_ids: set[str], vocabulary: set[str]) -> list[str]:
    """`teach`: a list of {concept, gap, remedy, figure, example?, builds_on_concept?}."""
    teach = card.get("teach")
    if teach is None:
        return []
    if not isinstance(teach, list) or not teach:
        return [f"{where}: teach must be a non-empty list"]
    errors: list[str] = []
    concepts = [e.get("concept") for e in teach if isinstance(e, dict)]
    for i, entry in enumerate(teach):
        at = f"{where}: teach[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{at} is not a mapping")
            continue
        for key in sorted(TEACH_KEYS - set(entry)):
            errors.append(f"{at} lacks {key}")
        for key in sorted(set(entry) - TEACH_KEYS - TEACH_OPTIONAL):
            errors.append(f"{at} has unknown key {key}")
        if entry.get("concept") not in vocabulary:
            errors.append(f"{at}: concept {entry.get('concept')!r} not in the index vocabulary")
        if entry.get("figure") not in figure_ids:
            errors.append(f"{at}: figure {entry.get('figure')!r} is not one of the card's figures")
        dep = entry.get("builds_on_concept")
        if dep is not None and dep not in concepts:
            errors.append(f"{at}: builds_on_concept {dep!r} is not a teach concept of this card")
    return errors


def _check_pypsa_example(where: str, example: dict, rows: dict, dirs: set[str]) -> list[str]:
    """`pypsa_example`: {model, why, figures}, the model a toy model and its figure ids."""
    import yaml

    if not isinstance(example, dict) or set(example) != {"model", "why", "figures"}:
        return [f"{where}: pypsa_example must be {{model, why, figures}}"]
    slug = example["model"]
    if slug not in dirs or slug not in rows:
        return [f"{where}: pypsa_example model {slug!r} is not a toy model"]
    other = yaml.safe_load((TOYMODELS / slug / "card.yaml").read_text())
    ids = {f["id"] for f in other.get("figures") or []}
    return [
        f"{where}: pypsa_example figure {fid!r} is not a figure of {slug}"
        for fid in example.get("figures") or []
        if fid not in ids
    ]


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
        for key in sorted(keys - TOYMODEL_CARD_KEYS - TOYMODEL_OPTIONAL):
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
        errors += _check_teach(where, card, set(card_figs), vocabulary)
        example = card.get("pypsa_example")
        if example is not None:
            errors += _check_pypsa_example(where, example, rows, dirs)
        if row.get("pypsa_example") != (example or {}).get("model"):
            errors.append(f"{where}: pypsa_example differs between card and index")
        meta_figs = set((results.get("meta") or {}).get("figures") or {})
        if meta_figs and meta_figs != set(card_figs):
            errors.append(f"{where}: results.yaml figures {sorted(meta_figs)} differ from the card")
    return errors


SCRIPT_LITERAL = re.compile(r"""\bscript:\s*(["'])(.+?)\1""")


def validate_payloads(root: Path) -> list[str]:
    """Every `methods/*/payload/pypsa-eur/` is a config fragment plus new rules and scripts.

    `config.yaml` is a mapping, `new/rules/` holds `*.smk`, there is no `edits/`, and no
    `script:` string literal in a rule resolves outside `new/` (the overlay root, where
    `rules/x.smk` sits beside `scripts/`) (`scripts(...)`
    helper calls are checkout references and are not checked). `pypsa-earth` is not scanned.
    """
    import yaml

    errors: list[str] = []
    for payload in sorted(root.glob("methods/*/payload/pypsa-eur")):
        if not payload.is_dir():
            continue
        where = str(payload.relative_to(root))
        if (payload / "edits").exists():
            errors.append(f"{where}: edits/ is gone, a payload only adds new/ files")
        config = payload / "config.yaml"
        if not config.is_file():
            errors.append(f"{where}: config.yaml missing")
        else:
            try:
                doc = yaml.safe_load(config.read_text())
            except yaml.YAMLError as exc:
                errors.append(f"{where}: config.yaml does not parse ({exc})")
            else:
                if not isinstance(doc, dict):
                    errors.append(f"{where}: config.yaml must be a mapping")
        rules_dir = payload / "new" / "rules"
        rules = sorted(rules_dir.glob("*.smk")) if rules_dir.is_dir() else []
        if not rules_dir.is_dir():
            errors.append(f"{where}: new/rules/ missing")
        elif not rules:
            errors.append(f"{where}: new/rules/ holds no *.smk")
        for rule in rules:
            for match in SCRIPT_LITERAL.finditer(rule.read_text()):
                target = posixpath.normpath(
                    posixpath.join(rule.parent.relative_to(payload / "new").as_posix(), match.group(2))
                )
                if target == ".." or target.startswith("../") or posixpath.isabs(target):
                    errors.append(
                        f"{where}/new/rules/{rule.name}: script {match.group(2)!r} "
                        "resolves outside new/"
                    )
    return errors


def main() -> int:
    r = load_restructure()
    r.ANCHORS["pypsa-eur"] = EUR_ANCHOR
    # .claude/, .github/, CLAUDE.md, pytest.ini, tools/ and toymodels/ postdate the frozen
    # TOP_LEVEL set; baselines/ was removed on 2026-09-11 when the app dropped baseline runs.
    r.TOP_LEVEL |= {".claude", ".github", "CLAUDE.md", "pytest.ini", "tools", "toymodels"}
    r.TOP_LEVEL -= {"baselines"}
    # The frozen slug list is the seven topics of the 2026-09 restructure; the
    # sector and security doors added on 2026-10-07 extend it here.
    r.TOPIC_SLUGS = r.TOPIC_SLUGS + (
        "hydrogen-grid",
        "municipal-heat",
        "industrial-decarbonisation",
        "e-fuels",
        "carbon-management",
        "transport-electrification",
        "security-of-supply",
    )
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
    errors += validate_payloads(ROOT)
    for e in errors:
        print("ERROR", e)
    print("ok" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
