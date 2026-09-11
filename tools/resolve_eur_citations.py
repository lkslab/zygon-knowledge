#!/usr/bin/env python3
"""Alignment gate: every pypsa-eur citation must resolve in the models/pypsa-eur checkout.

Walks the pypsa-eur section of every card under carriers/, topics/, methods/ and
data_quality/pypsa-eur/, extracts citations of the forms

    scripts/<file>.py:<symbol>      rules/<file>.smk:<rule>      config/config.default.yaml:<key>

plus bare `scripts/…`, `rules/…`, `config/…` paths, and checks each against the
submodule tree: the file must exist, the symbol string must occur in it, and a config key
must be a mapping key somewhere in config.default.yaml. It also scans
baselines/pypsa-eur/ and methods/*/payload/pypsa-eur/ for paths that no longer exist.
pypsa-earth sections are never looked at.

Exit status is non-zero on any miss. Use --list to print every citation it checks.

    python3 tools/resolve_eur_citations.py [--list] [--model-dir models/pypsa-eur]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODEL = "pypsa-eur"

# `data/` is not checked: those files are fetched by retrieve rules, not tracked upstream.
PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_/.-])((?:scripts|rules|config)/[A-Za-z0-9_./-]+\.(?:py|smk|yaml|json))"
    r"(?::([A-Za-z_][A-Za-z0-9_.-]*))?"
)
SNAKEFILE_RE = re.compile(r"(?<![A-Za-z0-9_/.-])Snakefile(?::([A-Za-z_][A-Za-z0-9_]*))?")
# User-authored files the workflow expects but does not ship.
USER_FILES = {"config/config.yaml", "config/scenarios.yaml"}


def eur_section(doc: Any) -> Any:
    """The pypsa-eur part of a card, or None. Never returns earth content."""
    if not isinstance(doc, dict):
        return None
    models = doc.get("models")
    if isinstance(models, list):
        return [m for m in models if isinstance(m, dict) and m.get("model") == MODEL] or None
    if isinstance(models, dict):
        return models.get(MODEL)
    if MODEL in doc:
        return doc[MODEL]
    return None


def card_files() -> list[Path]:
    out: list[Path] = []
    for pat in ("carriers/*/*.yaml", "topics/*.yaml", "methods/*.yaml", "methods/*/spec.yaml"):
        out += sorted(ROOT.glob(pat))
    return out


def eur_only_files() -> list[Path]:
    out = sorted((ROOT / "data_quality" / MODEL).rglob("*.yaml"))
    out += sorted((ROOT / "baselines" / MODEL).glob("*.yaml"))
    for p in sorted(ROOT.glob(f"methods/*/payload/{MODEL}")):
        out += sorted(x for x in p.rglob("*") if x.is_file())
    return out


def config_keys(path: Path) -> set[str]:
    keys: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                keys.add(str(k))
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(yaml.safe_load(path.read_text()))
    return keys


class Resolver:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self.cache: dict[str, str | None] = {}
        self.cfg_keys = config_keys(model_dir / "config" / "config.default.yaml")
        self.misses: dict[str, list[str]] = defaultdict(list)
        self.checked: set[tuple[str, str]] = set()
        # files a method payload adds to the model tree (methods/*/payload/pypsa-eur/new/)
        self.payload_new = sorted(ROOT.glob(f"methods/*/payload/{MODEL}/new"))

    def text_of(self, rel: str) -> str | None:
        if rel not in self.cache:
            p = self.model_dir / rel
            if not p.is_file():
                for base in self.payload_new:
                    if (base / rel).is_file():
                        p = base / rel
                        break
            self.cache[rel] = p.read_text(errors="replace") if p.is_file() else None
        return self.cache[rel]

    def check(self, source: str, rel: str, sym: str | None) -> None:
        self.checked.add((rel, sym or ""))
        if rel in USER_FILES:
            return
        text = self.text_of(rel)
        if text is None:
            self.misses[source].append(f"{rel} (file missing)")
            return
        if not sym:
            return
        if rel == "config/config.default.yaml":
            leaf = sym.split(".")[-1]
            if leaf not in self.cfg_keys:
                self.misses[source].append(f"{rel}:{sym} (config key missing)")
            return
        needle = sym.split(".")[0]
        if needle not in text:
            self.misses[source].append(f"{rel}:{sym} (symbol missing)")

    def scan_text(self, source: str, text: str) -> None:
        for m in PATH_RE.finditer(text):
            self.check(source, m.group(1), m.group(2))
        for m in SNAKEFILE_RE.finditer(text):
            self.check(source, "Snakefile", m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model-dir", default=str(ROOT / "models" / MODEL))
    ap.add_argument("--list", action="store_true", help="print every citation checked")
    args = ap.parse_args()
    model_dir = Path(args.model_dir)
    if not (model_dir / "Snakefile").is_file():
        print(f"ERROR {model_dir} is not a pypsa-eur checkout (run git submodule update --init)")
        return 2

    res = Resolver(model_dir)
    n_files = 0
    for f in card_files():
        doc = yaml.safe_load(f.read_text())
        sec = eur_section(doc)
        if sec is None:
            continue
        n_files += 1
        res.scan_text(str(f.relative_to(ROOT)), yaml.dump(sec, allow_unicode=True))
    for f in eur_only_files():
        n_files += 1
        res.scan_text(str(f.relative_to(ROOT)), f.read_text(errors="replace"))

    if args.list:
        for rel, sym in sorted(res.checked):
            print(f"{rel}:{sym}" if sym else rel)
    total = sum(len(v) for v in res.misses.values())
    for src in sorted(res.misses):
        for miss in res.misses[src]:
            print(f"MISS {src}: {miss}")
    print(
        f"{n_files} eur sources, {len(res.checked)} unique citations, "
        f"{total} unresolved in {len(res.misses)} files"
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
