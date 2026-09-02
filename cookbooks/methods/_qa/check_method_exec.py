#!/usr/bin/env python3
"""Checker for v2 executable method specs (schema_version: 2) — see
METHOD_EXEC.schema.yaml. v1 files are counted as LEGACY (pending manual
conversion) and skipped; they stay covered by check_methods.py until
converted. TEMPLATE.yaml is ignored.

Checks per v2 file:
  1  id == filename; required top-level fields; prose caps (what<=600,
     notes<=800, when_to_use<=4 entries)
  2  models[] non-empty; model enum; version_anchor.ref prefix matches the
     submodule HEAD; status in {draft, verified}
  3  baseline (if set) exists under fixtures/recipes/baseline-<model>/
  4  execution: 1..8 steps; kind enum; per-kind required fields; note<=200,
     do<=300; config keys resolve as dot-paths in the model default config;
     `where` anchors: file exists AND symbol greps (file:symbol, no line
     numbers); data targets are model-relative paths
  5  invalidates: rule names exist in the model's Snakefile/rules/*.smk
  6  success_metric: >=1; needs in {prepared, solved} (pair rejected until
     supported); check compiles as a python expression; expect<=200
  7  payload steps (dir-form methods, <slug>/spec.yaml): payload/<model>/
     exists and is non-empty; every edits/*.patch dry-applies against the
     pinned template (the drift oracle at epoch bumps); new/ files are new
Exit 0 iff all v2 files pass. LEGACY files never fail the run.

Usage: python3 cookbooks/methods/_qa/check_method_exec.py [--only slug ...]
# zygon-native (2026-07-31): model roots resolve to <zygon>/models/<model>;
# override root with ZYGON_MODELS
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = os.path.dirname(QA_DIR)
ZYGON = os.path.dirname(os.path.dirname(BOOK_DIR))
MODELS_ROOT = os.environ.get("ZYGON_MODELS", os.path.join(ZYGON, "models"))

MODELS = ("pypsa-eur", "pypsa-earth")
KINDS = ("config", "code", "rule", "data", "invocation", "payload")
NEEDS = ("prepared", "solved")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINENO_RE = re.compile(r"(:\d+\s*$|#L\d+)")
CAPS = {"what": 600, "notes": 800, "note": 200, "do": 300, "expect": 200}


def model_head(model):
    p = subprocess.run(["git", "-C", os.path.join(MODELS_ROOT, model),
                        "rev-parse", "HEAD"], capture_output=True, text=True)
    return p.stdout.strip()


def default_config(model):
    for rel in ("config/config.default.yaml", "config.default.yaml"):
        p = os.path.join(MODELS_ROOT, model, rel)
        if os.path.isfile(p):
            with open(p) as f:
                return yaml.safe_load(f)
    return None


def dotpath_exists(cfg, path):
    node = cfg
    for part in path.split("."):
        if isinstance(node, dict):
            if part in node:
                node = node[part]
            elif part.isdigit() and int(part) in node:
                node = node[int(part)]
            else:
                return False
        else:
            return False
    return True


def rule_names(model):
    names = set()
    root = os.path.join(MODELS_ROOT, model)
    files = glob.glob(os.path.join(root, "rules", "*.smk")) + \
        [os.path.join(root, "Snakefile")]
    for f in files:
        if os.path.isfile(f):
            with open(f, errors="replace") as fh:
                # \s* prefix: earth nests rules inside `if config[...]`
                # blocks (foresight branches), indented four spaces
                names |= set(re.findall(r"^\s*rule\s+(\w+)\s*:",
                                        fh.read(), re.M))
    return names


def check_where(model, where, errs, ctx):
    if LINENO_RE.search(where):
        errs.append(f"{ctx}: `where` carries a line number: {where!r}")
        return
    file, _, symbol = where.partition(":")
    if not symbol:
        errs.append(f"{ctx}: `where` must be file:symbol, got {where!r}")
        return
    path = os.path.join(MODELS_ROOT, model, file)
    if not os.path.isfile(path):
        errs.append(f"{ctx}: where-file not in model repo: {file}")
        return
    with open(path, errors="replace") as fh:
        if symbol not in fh.read():
            errs.append(f"{ctx}: symbol {symbol!r} does not grep in {file}")


def payload_assets(slug, model):
    """(new_files, patches) under <book>/<slug>/payload/<model>/, as
    relative-to-payload-root and absolute paths respectively."""
    root = os.path.join(BOOK_DIR, slug, "payload", model)
    new_files, patches = [], []
    new_root = os.path.join(root, "new")
    for dirpath, _, fnames in os.walk(new_root):
        for f in fnames:
            new_files.append(os.path.relpath(os.path.join(dirpath, f),
                                             new_root))
    patches = sorted(glob.glob(os.path.join(root, "edits", "*.patch")))
    return new_files, patches


def _patch_file_segment(patch_text, relpath):
    """The unified-diff segment(s) of one target file inside a multi-file
    patch, or '' when the patch does not touch it."""
    out, keep = [], False
    for line in patch_text.splitlines(keepends=True):
        if line.startswith("--- "):
            keep = False
        if line.startswith(f"--- a/{relpath}"):
            keep = True
        if keep:
            out.append(line)
    return "".join(out)


def payload_view(slug, model):
    """The payload's additions to the model's config surface and rule set:
    (cfg_dict | None, rule_names). A payload that patches the default
    config or ships/patches rule files INTRODUCES keys and rules that the
    spec's config steps and `invalidates` may legitimately reference —
    lookups must run against the patched view, not the pristine template."""
    root = os.path.join(BOOK_DIR, slug, "payload", model)
    new_files, patches = payload_assets(slug, model)
    rule_re = re.compile(r"^\+?\s*rule\s+(\w+)\s*:", re.M)
    rules = set()
    for rel in new_files:
        if rel.endswith(".smk") or os.path.basename(rel) == "Snakefile":
            with open(os.path.join(root, "new", rel),
                      errors="replace") as fh:
                rules |= set(rule_re.findall(fh.read()))
    cfg_rel = next((r for r in ("config/config.default.yaml",
                                "config.default.yaml")
                    if os.path.isfile(os.path.join(MODELS_ROOT, model, r))),
                   None)
    cfg = None
    seg_all = []
    for patch in patches:
        with open(patch, errors="replace") as fh:
            text = fh.read()
        rules |= {m for m in rule_re.findall(text)}
        if cfg_rel:
            seg = _patch_file_segment(text, cfg_rel)
            if seg:
                seg_all.append(seg)
    if cfg_rel and seg_all:
        with tempfile.TemporaryDirectory() as td:
            dst = os.path.join(td, cfg_rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(MODELS_ROOT, model, cfg_rel), dst)
            os.chmod(dst, 0o644)
            ok = True
            for seg in seg_all:
                p = subprocess.run(
                    ["patch", "-p1", "--batch", "--forward"],
                    input=seg, cwd=td, capture_output=True, text=True)
                ok = ok and p.returncode == 0
            if ok:
                with open(dst) as fh:
                    cfg = yaml.safe_load(fh)
    return cfg, rules


def check_payload(slug, model, errs, warns, ctx):
    """A `payload` step promises pre-tested assets: the dir must exist and
    be non-empty, every patch must dry-apply against the pinned template
    (patch -p1 --dry-run — THE drift oracle at epoch bumps), and new/
    files should be genuinely new."""
    root = os.path.join(BOOK_DIR, slug, "payload", model)
    if not os.path.isdir(root):
        errs.append(f"{ctx}: payload step but no payload/{model}/ dir")
        return
    new_files, patches = payload_assets(slug, model)
    if not new_files and not patches:
        errs.append(f"{ctx}: payload/{model}/ carries no new/ files and "
                    "no edits/*.patch")
        return
    mroot = os.path.join(MODELS_ROOT, model)
    for rel in new_files:
        if os.path.exists(os.path.join(mroot, rel)):
            warns.append(f"{ctx}: payload new/{rel} already exists in the "
                         "template — full replacement should be a patch")
    for patch in patches:
        p = subprocess.run(["patch", "-p1", "--batch", "--forward",
                            "--dry-run", "-i", patch],
                           cwd=mroot, capture_output=True, text=True)
        if p.returncode != 0:
            tail = (p.stderr or p.stdout).strip()[:200]
            errs.append(f"{ctx}: payload patch {os.path.basename(patch)} "
                        f"does not apply to the template: {tail}")


def check_file(path, slug, heads, cfgs, rules):
    errs, warns = [], []
    doc = yaml.safe_load(open(path))
    if doc.get("id") != slug:
        errs.append(f"id {doc.get('id')!r} != filename slug {slug!r}")
    if not SLUG_RE.match(slug):
        errs.append(f"filename not kebab-case: {slug}")
    for field in ("title", "what", "models"):
        if not doc.get(field):
            errs.append(f"missing required field '{field}'")
    for field, cap in (("what", CAPS["what"]), ("notes", CAPS["notes"])):
        v = doc.get(field)
        if isinstance(v, str) and len(v) > cap:
            errs.append(f"'{field}' over cap: {len(v)} > {cap} chars — "
                        "overflow belongs in _qa/paper_methods/")
    if len(doc.get("when_to_use") or []) > 4:
        errs.append("when_to_use: more than 4 entries")

    for i, sec in enumerate(doc.get("models") or []):
        ctx = f"models[{i}]"
        model = sec.get("model")
        if model not in MODELS:
            errs.append(f"{ctx}: model must be one of {MODELS}")
            continue
        anchor = (sec.get("version_anchor") or {}).get("ref", "")
        if not heads[model].startswith(anchor[:12]) or not anchor:
            errs.append(f"{ctx}: version_anchor.ref does not match submodule "
                        f"HEAD {heads[model][:12]}")
        if sec.get("status") not in ("draft", "verified"):
            errs.append(f"{ctx}: status must be draft|verified")
        b = sec.get("baseline")
        if b and not os.path.isfile(os.path.join(
                ZYGON, "fixtures", "recipes", f"baseline-{model}", b)):
            errs.append(f"{ctx}: baseline {b!r} not in fixtures")
        steps = sec.get("execution") or []
        if not 1 <= len(steps) <= 8:
            errs.append(f"{ctx}: execution needs 1..8 steps, has {len(steps)}")
        # a payload may introduce config keys and rules — resolve config
        # steps and `invalidates` against the payload-patched view
        eff_cfg, eff_rules = cfgs[model], rules[model]
        if any(st.get("kind") == "payload" for st in steps):
            pcfg, prules = payload_view(slug, model)
            eff_cfg = pcfg if pcfg is not None else eff_cfg
            eff_rules = eff_rules | prules
        for j, st in enumerate(steps):
            sctx = f"{ctx}.execution[{j}]"
            kind = st.get("kind")
            if kind not in KINDS:
                errs.append(f"{sctx}: kind must be one of {KINDS}")
                continue
            for fld in ("note", "do"):
                v = st.get(fld)
                if isinstance(v, str) and len(v) > CAPS[fld]:
                    errs.append(f"{sctx}: '{fld}' over {CAPS[fld]} chars")
            if kind == "config":
                key = st.get("key")
                if not key:
                    errs.append(f"{sctx}: config step needs `key`")
                elif eff_cfg and not dotpath_exists(eff_cfg, key):
                    errs.append(f"{sctx}: key {key!r} not in {model} "
                                "default config (payload patches included)")
                if "value" not in st:
                    errs.append(f"{sctx}: config step needs `value`")
            elif kind in ("code", "rule"):
                if not st.get("where"):
                    errs.append(f"{sctx}: {kind} step needs `where`")
                else:
                    check_where(model, st["where"], errs, sctx)
                if not st.get("do"):
                    errs.append(f"{sctx}: {kind} step needs `do`")
            elif kind == "data":
                if not st.get("target"):
                    errs.append(f"{sctx}: data step needs `target`")
                if not st.get("do"):
                    errs.append(f"{sctx}: data step needs `do`")
        has_payload_step = any(st.get("kind") == "payload" for st in steps)
        payload_root = os.path.join(BOOK_DIR, slug, "payload", model)
        if has_payload_step:
            check_payload(slug, model, errs, warns, ctx)
        elif os.path.isdir(payload_root):
            warns.append(f"{ctx}: payload/{model}/ exists but no payload "
                         "step declares it — dead assets")
        for rname in sec.get("invalidates") or []:
            if rname not in eff_rules:
                errs.append(f"{ctx}: invalidates rule {rname!r} not found in "
                            f"{model} Snakefile/rules (payload included)")
        metrics = sec.get("success_metric") or []
        if not metrics:
            errs.append(f"{ctx}: success_metric required (>=1)")
        for j, m in enumerate(metrics):
            mctx = f"{ctx}.success_metric[{j}]"
            if m.get("needs") == "pair":
                errs.append(f"{mctx}: needs=pair reserved, not yet supported "
                            "— write a one-run metric")
            elif m.get("needs") not in NEEDS:
                errs.append(f"{mctx}: needs must be one of {NEEDS}")
            expr = m.get("check")
            if not expr:
                errs.append(f"{mctx}: missing `check` expression")
            else:
                try:
                    compile(expr, mctx, "eval")
                except SyntaxError as e:
                    errs.append(f"{mctx}: check does not compile: {e}")
            v = m.get("expect")
            if isinstance(v, str) and len(v) > CAPS["expect"]:
                errs.append(f"{mctx}: 'expect' over {CAPS['expect']} chars")
            if not m.get("name"):
                errs.append(f"{mctx}: missing `name`")
    return errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    heads = {m: model_head(m) for m in MODELS}
    cfgs = {m: default_config(m) for m in MODELS}
    rules = {m: rule_names(m) for m in MODELS}

    # a method is <slug>.yaml, or <slug>/spec.yaml when it ships assets;
    # unconverted v1 essays live in v1/ and count as legacy
    specs = [(os.path.basename(p)[:-5], p)
             for p in glob.glob(os.path.join(BOOK_DIR, "*.yaml"))
             + glob.glob(os.path.join(BOOK_DIR, "v1", "*.yaml"))]
    specs += [(os.path.basename(os.path.dirname(p)), p)
              for p in glob.glob(os.path.join(BOOK_DIR, "*", "spec.yaml"))
              if os.path.basename(os.path.dirname(p)) not in ("_qa", "v1")]

    v2, legacy, failed = 0, 0, 0
    for slug, path in sorted(specs):
        if slug == "TEMPLATE":
            continue
        if args.only and slug not in args.only:
            continue
        try:
            doc = yaml.safe_load(open(path))
        except yaml.YAMLError as e:
            print(f"FAIL {slug}: unparseable: {e}")
            failed += 1
            continue
        if not isinstance(doc, dict) or doc.get("schema_version") != 2:
            legacy += 1
            continue
        if os.path.basename(os.path.dirname(path)) == "v1":
            print(f"FAIL {slug}: v2 exec spec filed under v1/ — move it up")
            failed += 1
            continue
        v2 += 1
        errs, warns = check_file(path, slug, heads, cfgs, rules)
        for w in warns:
            print(f"  warn {slug}: {w}")
        if errs:
            failed += 1
            print(f"FAIL {slug}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"ok   {slug}")
    print(f"-- v2: {v2 - failed}/{v2} pass; legacy pending conversion: "
          f"{legacy}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
