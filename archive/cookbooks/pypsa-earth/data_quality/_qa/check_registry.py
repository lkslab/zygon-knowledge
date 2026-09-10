# -*- coding: utf-8 -*-
"""
QA for the data-quality cookbook: registry <-> recipes <-> scorecards consistency.

Checks:
  1. datasets.yaml parses; required fields per entry; ids unique
  2. every `consumer` provenance is file:symbol, file exists in the repo, each
     symbol occurs verbatim (grep -F); no line numbers, no URLs
  3. every `used_by` slug is an existing recipe in generation_conversion/ or demand/
  4. every `path` exists on disk (or entry notes it is runtime-fetched)
  5. tier_when_missing in {A,B,C,D}; coverage_class/code_convention in vocab
  6. scorecards (if generated): parse, dataset ids ⊆ registry ids, grades valid;
     MATRIX.csv rows == number of scorecards, cols == registry ids

Usage: python3 cookbooks/pypsa-earth/data_quality/_qa/check_registry.py
       (from the zygon repo root)
"""

import os
import re
import sys

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = os.path.dirname(QA_DIR)
COOKBOOKS = os.path.dirname(BOOK_DIR)  # <zygon>/cookbooks/<model>: holds the sibling recipe books
# zygon-native (2026-07-31): model roots resolve to <zygon>/models/<model>; override root with ZYGON_MODELS
_dir, _child = QA_DIR, None
while os.path.basename(_dir) != "cookbooks":
    if os.path.dirname(_dir) == _dir:
        sys.exit(f"cannot locate 'cookbooks' above {QA_DIR}")
    _dir, _child = os.path.dirname(_dir), os.path.basename(_dir)
ZYGON_ROOT = os.path.dirname(_dir)
COOKBOOK_MODEL = _child  # path segment after 'cookbooks'
REPO = os.path.join(
    os.environ.get("ZYGON_MODELS", os.path.join(ZYGON_ROOT, "models")), COOKBOOK_MODEL)

CODE_CONVENTIONS = {"ISO2", "ISO3", "country-name", "geofabrik", "continent", "gridded", "global"}
COVERAGE_CLASSES = {"country-listed", "global-listed", "global-gridded", "proxy-global", "continent-file"}
LINENO_RE = re.compile(r"(:\d+\s*$|#L\d+)")

errors = []


def err(msg):
    errors.append(msg)


def check_provenance(value, label):
    if not isinstance(value, str) or ":" not in value:
        err(f"{label}: consumer not 'file:symbol' ({value!r})")
        return
    if "http" in value:
        err(f"{label}: URL in consumer provenance")
        return
    if LINENO_RE.search(value):
        err(f"{label}: line number in consumer provenance ({value!r})")
        return
    for entry in value.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        fpath, _, symbol = entry.partition(":")
        full = os.path.join(REPO, fpath.strip())
        if not os.path.isfile(full):
            err(f"{label}: consumer file missing: {fpath}")
            continue
        with open(full, errors="replace") as f:
            content = f.read()
        for part in [s.strip() for s in re.split(r" / |, | and ", symbol) if s.strip()]:
            if part not in content:
                err(f"{label}: symbol {part!r} not found in {fpath}")


def recipe_slugs():
    slugs = set()
    for book in ("generation_conversion", "demand"):
        d = os.path.join(COOKBOOKS, book)
        slugs.update(
            os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".yaml"))
    return slugs


def main():
    reg_path = os.path.join(BOOK_DIR, "datasets.yaml")
    registry = yaml.safe_load(open(reg_path))
    if not isinstance(registry, list):
        print("FATAL: datasets.yaml top level must be a list")
        sys.exit(1)

    ids = [d.get("id") for d in registry]
    if len(set(ids)) != len(ids):
        err("duplicate dataset ids")

    slugs = recipe_slugs()
    for d in registry:
        label = d.get("id", "<no-id>")
        for key in ("id", "title", "path", "code_convention", "coverage_class",
                    "consumer", "missing_behavior", "tier_when_missing", "used_by"):
            if key not in d:
                err(f"{label}: missing field {key}")
        if d.get("code_convention") not in CODE_CONVENTIONS:
            err(f"{label}: bad code_convention {d.get('code_convention')!r}")
        if d.get("coverage_class") not in COVERAGE_CLASSES:
            err(f"{label}: bad coverage_class {d.get('coverage_class')!r}")
        if d.get("tier_when_missing") not in {"A", "B", "C", "D"}:
            err(f"{label}: bad tier_when_missing {d.get('tier_when_missing')!r}")
        if "consumer" in d:
            check_provenance(d["consumer"], label)
        paths = d.get("path")
        paths = paths if isinstance(paths, list) else [paths]
        runtime_ok = "runtime" in str(d.get("notes", "")).lower()
        for path in paths:
            if not path or runtime_ok:
                continue
            spath = str(path)
            if "<" in spath or "*" in spath:
                # template path: substitute placeholders with a glob and require >=1 match
                import glob as _glob
                pattern = re.sub(r"<[^>]+>", "*", spath)
                if not _glob.glob(os.path.join(REPO, pattern)):
                    err(f"{label}: template path matches nothing on disk: {path}")
            elif not os.path.exists(os.path.join(REPO, spath)):
                err(f"{label}: path not on disk (and notes don't say runtime-fetched): {path}")
        for slug in d.get("used_by", []):
            if slug not in slugs:
                err(f"{label}: used_by slug not found in cookbooks: {slug}")

    # scorecards, if generated
    cdir = os.path.join(BOOK_DIR, "countries")
    cards = sorted(f for f in os.listdir(cdir) if f.endswith(".yaml")) \
        if os.path.isdir(cdir) else []
    idset = set(ids)
    for fname in cards:
        card = yaml.safe_load(open(os.path.join(cdir, fname)))
        if card.get("country") != os.path.splitext(fname)[0]:
            err(f"{fname}: country != filename stem")
        for ds, info in (card.get("datasets") or {}).items():
            if ds not in idset:
                err(f"{fname}: dataset {ds} not in registry")
            if info.get("grade") not in {"A", "B", "C", "D"}:
                err(f"{fname}: bad grade for {ds}")

    matrix = os.path.join(BOOK_DIR, "MATRIX.csv")
    if cards and os.path.isfile(matrix):
        import pandas as pd
        m = pd.read_csv(matrix, index_col=0)
        if len(m) != len(cards):
            err(f"MATRIX rows ({len(m)}) != scorecards ({len(cards)})")
        extra = set(m.columns) - idset
        if extra:
            err(f"MATRIX columns not in registry: {sorted(extra)}")

    if errors:
        print(f"FAIL ({len(errors)} problems)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"registry ok: {len(ids)} datasets; scorecards checked: {len(cards)}")


if __name__ == "__main__":
    main()
