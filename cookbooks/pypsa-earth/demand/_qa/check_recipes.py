# -*- coding: utf-8 -*-
"""
QA checker for the DEMAND cookbook (dual-model recipes).

Extends the generation_conversion checker per _qa/SCHEMA_NOTES.md:
  - 1-2 model sections, each 'pypsa-earth' or 'pypsa-eur' (no duplicates)
  - per-model repo roots: provenance files + lever config dot-paths resolve
    against the section's OWN repo and default config
  - per-model version anchors enforced
  - optional demand_dimensions (driver/spatial/temporal/scenario one-liners)
  - optional top-level reference_taxonomy (framework/concepts/sources URLs);
    URLs are allowed ONLY there, never in provenance
  - everything else as before: file:symbol provenance (grep -F verified, no
    line numbers), rungs L0-L5, where-anchors for L2+, no verification field

Usage:  python3 cookbooks/pypsa-earth/demand/_qa/check_recipes.py [--only slug ...]
        (from the zygon repo root)
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
_MODELS_ROOT = os.environ.get("ZYGON_MODELS", os.path.join(ZYGON_ROOT, "models"))
EARTH_REPO = os.path.join(_MODELS_ROOT, "pypsa-earth")
EUR_REPO = os.path.join(_MODELS_ROOT, "pypsa-eur")

MODELS = {
    "pypsa-earth": {
        "repo": EARTH_REPO,
        "config": os.path.join(EARTH_REPO, "config.default.yaml"),
        "ref_prefix": "8435f4c8",
    },
    "pypsa-eur": {
        "repo": EUR_REPO,
        "config": os.path.join(EUR_REPO, "config", "config.default.yaml"),
        "ref_prefix": "3e32e3c6",
    },
}

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RUNGS = {"L0", "L1", "L2", "L3", "L4", "L5"}
LINENO_RE = re.compile(r"(:\d+\s*$|#L\d+)")

_config_cache = {}


def load_config(model):
    path = MODELS[model]["config"]
    if path not in _config_cache:
        with open(path) as f:
            _config_cache[path] = yaml.safe_load(f)
    return _config_cache[path]


def dotpath_exists(cfg, path):
    node = cfg
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


def check_provenance(value, errors, label, repo_dir):
    """';'-separated 'file:symbol' entries resolved against repo_dir."""
    if not isinstance(value, str) or ":" not in value:
        errors.append(f"{label}: provenance not 'file:symbol' ({value!r})")
        return
    if "http://" in value or "https://" in value:
        errors.append(f"{label}: URLs are not allowed in provenance (use reference_taxonomy)")
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
        fpath, symbol = fpath.strip(), symbol.strip()
        full = os.path.join(repo_dir, fpath)
        if not os.path.isfile(full):
            errors.append(f"{label}: provenance file missing in {os.path.basename(repo_dir)}: {fpath}")
            continue
        if not symbol:
            errors.append(f"{label}: empty symbol in provenance ({entry!r})")
            continue
        try:
            with open(full, errors="replace") as f:
                content = f.read()
        except OSError as e:
            errors.append(f"{label}: cannot read {fpath} ({e})")
            continue
        parts = [p.strip() for p in re.split(r" / |, | and ", symbol) if p.strip()]
        for part in parts:
            if part not in content:
                errors.append(f"{label}: symbol {part!r} not found verbatim in {fpath}")


def check_model_section(m, errors, idx):
    model = m.get("model")
    if model not in MODELS:
        errors.append(f"models[{idx}]: model {model!r} not in {sorted(MODELS)}")
        return
    spec = MODELS[model]
    tag = f"[{model}]"

    va = m.get("version_anchor", {})
    if not str(va.get("ref", "")).startswith(spec["ref_prefix"]):
        errors.append(f"{tag} version_anchor.ref {va.get('ref')!r} does not start {spec['ref_prefix']}")
    if "date" not in va:
        errors.append(f"{tag} version_anchor.date missing")

    oob = m.get("out_of_box")
    if not isinstance(oob, dict):
        errors.append(f"{tag} out_of_box missing or not a mapping")
    else:
        for key in ("covers", "mechanism", "not_covered", "provenance"):
            if key not in oob:
                errors.append(f"{tag} out_of_box.{key} missing")
        if "provenance" in oob:
            check_provenance(oob["provenance"], errors, f"{tag} out_of_box", spec["repo"])

    cfg = load_config(model)
    for i, lever in enumerate(m.get("levers") or []):
        label = f"{tag} levers[{i}]"
        for key in ("key", "effect", "default", "provenance"):
            if key not in lever:
                errors.append(f"{label}.{key} missing")
        if "key" in lever and not dotpath_exists(cfg, str(lever["key"])):
            errors.append(f"{label}.key not found in {model} default config: {lever['key']!r}")
        if "provenance" in lever:
            check_provenance(lever["provenance"], errors, label, spec["repo"])

    max_rung = -1
    for i, b in enumerate(m.get("boundary") or []):
        label = f"{tag} boundary[{i}]"
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
        errors.append(f"{tag} boundary has rungs >= L2 but `where` is missing/empty")
    for i, w in enumerate(m.get("where") or []):
        label = f"{tag} where[{i}]"
        for key in ("change", "anchor", "provenance"):
            if key not in w:
                errors.append(f"{label}.{key} missing")
        if "provenance" in w:
            check_provenance(w["provenance"], errors, label, spec["repo"])

    dd = m.get("demand_dimensions")
    if dd is not None:
        if not isinstance(dd, dict):
            errors.append(f"{tag} demand_dimensions must be a mapping")
        else:
            for key in ("driver", "spatial", "temporal", "scenario"):
                if not dd.get(key):
                    errors.append(f"{tag} demand_dimensions.{key} missing/empty")


def check_file(path):
    errors = []
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path) as f:
            doc = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]
    if not isinstance(doc, dict):
        return ["top level is not a mapping"]

    for key in ("id", "title", "summary", "when_to_use", "models"):
        if key not in doc:
            errors.append(f"missing required key: {key}")
    if errors:
        return errors

    if doc["id"] != stem:
        errors.append(f"id {doc['id']!r} != filename stem {stem!r}")
    if not SLUG_RE.match(str(doc["id"])):
        errors.append(f"id not kebab-case: {doc['id']!r}")
    if not isinstance(doc["when_to_use"], list) or not doc["when_to_use"]:
        errors.append("when_to_use must be a non-empty list")

    models = doc["models"]
    if not isinstance(models, list) or not (1 <= len(models) <= 2):
        errors.append("models must be a list with 1-2 entries")
        return errors
    names = [m.get("model") for m in models]
    if len(set(names)) != len(names):
        errors.append(f"duplicate model sections: {names}")
    for idx, m in enumerate(models):
        check_model_section(m, errors, idx)

    rt = doc.get("reference_taxonomy")
    if rt is not None:
        if not isinstance(rt, dict):
            errors.append("reference_taxonomy must be a mapping")
        else:
            if not rt.get("framework"):
                errors.append("reference_taxonomy.framework missing/empty")
            if not isinstance(rt.get("concepts"), list) or not rt.get("concepts"):
                errors.append("reference_taxonomy.concepts must be a non-empty list")
            srcs = rt.get("sources")
            if not isinstance(srcs, list) or not srcs:
                errors.append("reference_taxonomy.sources must be a non-empty list")
            else:
                for s in srcs:
                    if not str(s).startswith(("http://", "https://")):
                        errors.append(f"reference_taxonomy.sources entry not a URL: {s!r}")

    if "verification" in doc or any("verification" in m for m in models):
        errors.append("recipes must not contain a verification field")

    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()

    files = sorted(
        f for f in os.listdir(RECIPES_DIR)
        if f.endswith(".yaml") and os.path.isfile(os.path.join(RECIPES_DIR, f))
    )
    if args.only:
        files = [f for f in files if os.path.splitext(f)[0] in set(args.only)]

    n_fail = 0
    for fname in files:
        errors = check_file(os.path.join(RECIPES_DIR, fname))
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
