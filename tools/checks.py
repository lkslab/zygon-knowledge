"""Checks the app's knowledge reader does not make: anchors, citations, payloads."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import yaml

from knowledge import CARRIER_BOOKS, Knowledge, KnowledgeError


def anchor_errors(handle: Knowledge, expected: str) -> list[str]:
    """Every topic, carrier and method section carries the canonical anchor."""
    model = handle.model
    keys = (
        [f"topics/{t.id}" for t in handle.topics()]
        + [f"carriers/{c.book}/{c.id}" for c in handle.carriers()]
        + [f"methods/{m.id}" for m in handle.methods()]
    )
    anchors = handle.anchors()
    errors: list[str] = []
    for key in keys:
        ref = anchors.get(key)
        if ref is None:
            errors.append(f"{key}/{model}: no version_anchor")
        elif ref != expected:
            errors.append(
                f"{key}/{model}: version_anchor {ref[:8]} is not the canonical {expected[:8]}"
            )
    return errors


def citation_errors(handle: Knowledge) -> list[str]:
    """Every method a topic cites resolves, and every method is cited by a topic."""
    model = handle.model
    errors: list[str] = []
    cited: set[str] = set()
    for topic in handle.topics():
        for ref in topic.section(model).methods:
            cited.add(ref.id)
            try:
                handle.method(ref.id)
            except KnowledgeError as exc:
                errors.append(f"topics/{topic.id}/{model}: method {ref.id}: {exc}")
    errors.extend(
        f"methods/{m.id}/{model}: not cited by any topic"
        for m in handle.methods()
        if m.id not in cited
    )
    return errors


def identity_errors(handle: Knowledge) -> list[str]:
    """Every listed card's `id` equals its file stem and holds one section per model."""
    root, model = handle.root, handle.model
    cards = [("topics", path, path.stem) for path in root.glob("topics/*.yaml")]
    cards += [
        ("carriers", path, path.stem)
        for book in CARRIER_BOOKS
        for path in root.glob(f"carriers/{book}/*.yaml")
    ]
    cards += [("methods", path, path.stem) for path in root.glob("methods/*.yaml")]
    cards += [("methods", path, path.parent.name) for path in root.glob("methods/*/spec.yaml")]
    errors: list[str] = []
    for kind, path, stem in sorted(cards):
        doc = yaml.safe_load(path.read_text())
        sections = [s for s in doc.get("models", []) if s.get("model") == model]
        if not sections:
            continue
        if doc.get("id") != stem:
            errors.append(f"{kind}/{stem}: id is '{doc.get('id')}'")
        if len(sections) > 1:
            errors.append(f"{kind}/{doc.get('id')}/{model}: {len(sections)} sections for the model")
    return errors


SCRIPT_LITERAL = re.compile(r"""\bscript:\s*(["'])(.+?)\1""")


def validate_payloads(root: Path) -> list[str]:
    """Every `methods/*/payload/pypsa-eur/` is a config fragment plus new rules and scripts.

    `config.yaml` is a mapping, `new/rules/` holds `*.smk`, there is no `edits/`, and no
    `script:` string literal in a rule resolves outside `new/` (the overlay root, where
    `rules/x.smk` sits beside `scripts/`) (`scripts(...)`
    helper calls are checkout references and are not checked). `pypsa-earth` is not scanned.
    """
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
