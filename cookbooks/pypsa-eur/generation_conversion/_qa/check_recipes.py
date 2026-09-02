# -*- coding: utf-8 -*-
# PORTED from /home/lukas/Desktop/earth/pypsa-earth/cookbooks/generation_conversion/_qa/check_recipes.py (2026-07-22).
# Changes: EXPECTED_MODEL pypsa-earth->pypsa-eur; EXPECTED_REF_PREFIX 8435f4c8->849c8858;
#          default config path config.default.yaml -> config/config.default.yaml.
"""
QA checker for the recipe book in recipes/.

Validates every recipes/*.yaml against the contract in
enderpearl/claude_instructions/recipes/RECIPE.schema.yaml:

  1. YAML parses; required keys id/title/summary/when_to_use/models present
  2. id == filename stem, kebab-case
  3. exactly one model section, model == "pypsa-eur",
     version_anchor.ref starts with the expected commit
  4. out_of_box carries covers/mechanism/not_covered/provenance
  5. every provenance is "file:symbol" — no line numbers; the file exists in the
     repo and the symbol occurs verbatim in it
  6. every levers[].key resolves as a dot-path in config/config.default.yaml
  7. boundary[].rung in L0..L5; `where` present when boundary has rungs >= L2

Usage:  python3 cookbooks/pypsa-eur/generation_conversion/_qa/check_recipes.py [--only slug ...]
        (from the zygon repo root)
Exit 0 iff all files pass. Prints a per-file pass/fail table.
"""

import argparse
import os
import re
import sys

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPES_DIR = os.path.dirname(QA_DIR)
# zygon-native (2026-07-31): model roots resolve to <zygon>/models/<model>; override root with ZYGON_MODELS
_dir, _child = QA_DIR, None
while os.path.basename(_dir) != "cookbooks":
    if os.path.dirname(_dir) == _dir:
        sys.exit(f"cannot locate 'cookbooks' above {QA_DIR}")
    _dir, _child = os.path.dirname(_dir), os.path.basename(_dir)
ZYGON_ROOT = os.path.dirname(_dir)
COOKBOOK_MODEL = _child  # path segment after 'cookbooks'
REPO_DIR = os.path.join(
    os.environ.get("ZYGON_MODELS", os.path.join(ZYGON_ROOT, "models")), COOKBOOK_MODEL)

EXPECTED_MODEL = "pypsa-eur"
EXPECTED_REF_PREFIX = "849c8858"
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RUNGS = {"L0", "L1", "L2", "L3", "L4", "L5"}
# reject provenance carrying line numbers: file.py:123, file.py#L123, symbol:45
LINENO_RE = re.compile(r"(:\d+\s*$|#L\d+)")


def load_default_config():
    with open(os.path.join(REPO_DIR, "config", "config.default.yaml")) as f:
        return yaml.safe_load(f)


def dotpath_exists(cfg, path):
    node = cfg
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


def check_provenance(value, errors, label):
    """provenance = 'file:symbol' entries, ';'-separated (schema encourages pointing
    at both the config schema entry and the consuming code). Each entry: the file
    exists and the symbol occurs verbatim in it."""
    if not isinstance(value, str) or ":" not in value:
        errors.append(f"{label}: provenance not 'file:symbol' ({value!r})")
        return
    if LINENO_RE.search(value):
        errors.append(f"{label}: provenance contains a line number ({value!r})")
        return
    for entry in value.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            errors.append(f"{label}: provenance entry not 'file:symbol' ({entry!r})")
            continue
        fpath, _, symbol = entry.partition(":")
        fpath = fpath.strip()
        full = os.path.join(REPO_DIR, fpath)
        if not os.path.isfile(full):
            errors.append(f"{label}: provenance file missing ({fpath})")
            continue
        symbol = symbol.strip()
        if not symbol:
            errors.append(f"{label}: empty symbol in provenance ({entry!r})")
            continue
        try:
            with open(full, errors="replace") as f:
                content = f.read()
        except OSError as e:
            errors.append(f"{label}: cannot read {fpath} ({e})")
            continue
        # compound symbols may use spaced separators: 'sym1 / sym2', 'a, b', 'a and b'
        parts = [p.strip() for p in re.split(r" / |, | and ", symbol) if p.strip()]
        for part in parts:
            if part not in content:
                errors.append(f"{label}: symbol {part!r} not found verbatim in {fpath}")


def check_file(path, cfg):
    errors = []
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path) as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]
    if not isinstance(doc, dict):
        return ["top level is not a mapping"]

    # 1. required keys
    for key in ("id", "title", "summary", "when_to_use", "models"):
        if key not in doc:
            errors.append(f"missing required key: {key}")
    if errors:
        return errors

    # 2. id/slug
    if doc["id"] != stem:
        errors.append(f"id {doc['id']!r} != filename stem {stem!r}")
    if not SLUG_RE.match(str(doc["id"])):
        errors.append(f"id not kebab-case: {doc['id']!r}")
    if not isinstance(doc["when_to_use"], list) or not doc["when_to_use"]:
        errors.append("when_to_use must be a non-empty list")

    # 3. model section
    models = doc["models"]
    if not isinstance(models, list) or len(models) != 1:
        errors.append("models must be a list with exactly one entry")
        return errors
    m = models[0]
    if m.get("model") != EXPECTED_MODEL:
        errors.append(f"model is {m.get('model')!r}, expected {EXPECTED_MODEL!r}")
    va = m.get("version_anchor", {})
    if not str(va.get("ref", "")).startswith(EXPECTED_REF_PREFIX):
        errors.append(f"version_anchor.ref {va.get('ref')!r} does not start {EXPECTED_REF_PREFIX}")
    if "date" not in va:
        errors.append("version_anchor.date missing")

    # 4. out_of_box
    oob = m.get("out_of_box")
    if not isinstance(oob, dict):
        errors.append("out_of_box missing or not a mapping")
    else:
        for key in ("covers", "mechanism", "not_covered", "provenance"):
            if key not in oob:
                errors.append(f"out_of_box.{key} missing")
        if "provenance" in oob:
            check_provenance(oob["provenance"], errors, "out_of_box")

    # 5+6. levers
    for i, lever in enumerate(m.get("levers") or []):
        label = f"levers[{i}]"
        for key in ("key", "effect", "default", "provenance"):
            if key not in lever:
                errors.append(f"{label}.{key} missing")
        if "key" in lever and not dotpath_exists(cfg, str(lever["key"])):
            errors.append(f"{label}.key not found in config/config.default.yaml: {lever['key']!r}")
        if "provenance" in lever:
            check_provenance(lever["provenance"], errors, label)

    # 7. boundary + where
    max_rung = -1
    for i, b in enumerate(m.get("boundary") or []):
        label = f"boundary[{i}]"
        rung = b.get("rung")
        if rung not in RUNGS:
            errors.append(f"{label}.rung invalid: {rung!r}")
        else:
            max_rung = max(max_rung, int(rung[1]))
        if not b.get("variant"):
            errors.append(f"{label}.variant empty")
        if not b.get("note"):
            errors.append(f"{label}.note empty")
    if max_rung >= 2 and not m.get("where"):
        errors.append("boundary contains rungs >= L2 but `where` is missing/empty")
    for i, w in enumerate(m.get("where") or []):
        label = f"where[{i}]"
        for key in ("change", "anchor", "provenance"):
            if key not in w:
                errors.append(f"{label}.{key} missing")
        if "provenance" in w:
            check_provenance(w["provenance"], errors, label)

    # forbidden: verification field (handled separately per EXTRACTION.md)
    if "verification" in doc or "verification" in m:
        errors.append("recipes must not contain a verification field")

    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="restrict to these slugs")
    args = ap.parse_args()

    cfg = load_default_config()
    files = sorted(
        f for f in os.listdir(RECIPES_DIR)
        if f.endswith(".yaml") and os.path.isfile(os.path.join(RECIPES_DIR, f))
    )
    if args.only:
        files = [f for f in files if os.path.splitext(f)[0] in set(args.only)]

    n_fail = 0
    for fname in files:
        errors = check_file(os.path.join(RECIPES_DIR, fname), cfg)
        if errors:
            n_fail += 1
            print(f"FAIL  {fname}")
            for e in errors:
                print(f"      - {e}")
        else:
            print(f"ok    {fname}")

    print(f"\n{len(files) - n_fail}/{len(files)} recipes pass")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
