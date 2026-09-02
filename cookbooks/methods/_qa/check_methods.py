# -*- coding: utf-8 -*-
"""
QA checker for the methods book — the mechanical form of the golden rule.

Validates every cookbooks/methods/*.yaml against _qa/METHOD.schema.yaml. Ports
check_provenance / dotpath_exists / SLUG_RE / LINENO_RE / RUNGS from
cookbooks/pypsa-eur/generation_conversion/_qa/check_recipes.py, with one structural
improvement: that checker resolves its repo root by walking two directories up from
the book, which was correct when cookbooks lived INSIDE a model repo and is wrong in
zygon (it lands on cookbooks/). Here both submodules are checked out under
<zygon>/models/, so each model section's provenance is greped against its own
submodule and no hardcoded ~/Desktop/... sibling path is needed. This is the first
cookbook checker that is properly self-contained.

Checks
  1  YAML parses; required keys present; id == filename stem; kebab-case; in SLUGS.yaml
  2  exactly two model sections (pypsa-eur, pypsa-earth); version_anchor.ref matches
     the live `git submodule status` SHA, so a moved submodule fails loudly
  3  provenance is file:symbol, NO line numbers, file exists in THAT model's repo and
     the symbol occurs verbatim (available / levers / assembly / where / procedure)
  4  levers[].key resolves as a dot-path in that model's default config
  5  functionality[].id and assembly[].uses resolve in that model's FUNCTIONALITY.yaml;
     warn on turnkey-verdict-citing-an-absent-capability
  6  literature[].paper exists in CORPUS.yaml and tier matches the directory
  7  boundary[].rung in L0..L5; `where` required at >=L2; data_dependencies at L3
  8  boundary[].variant joins variants[].id, both directions
  9  variants[].papers and pitfalls[].evidence are subsets of literature[].paper
 10  requires_methods / combines_with resolve to files in this book (cycle detection on
     requires_methods); topics resolve to cookbooks/pypsa-eur/topics/
 11  pypsa_primitive.symbol resolves in the pypsa env (skip-with-warning if absent —
     pypsa is a version pin, not a submodule); pypsa_version matches the installed dist
 12  prevalence arithmetic self-consistent
 13  enums valid (verdict, role, over, family)
 14  FORBIDDEN fields asserts/invalidates/out_of_box rejected explicitly, so a
     copy-pasted recipe fails loudly instead of being mis-executed by the referee

Usage:  python cookbooks/methods/_qa/check_methods.py [--only slug ...] [--no-warnings]
Env:    PYPSA_ENV  path to a python env containing pypsa (default: the earth pixi env)
Exit 0 iff all files pass. Warnings do not fail the run.
"""

import argparse
import glob
import os
import re
import subprocess
import sys

import yaml

QA_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = os.path.dirname(QA_DIR)                              # cookbooks/methods
COOKBOOKS_DIR = os.path.dirname(BOOK_DIR)                       # cookbooks
ZYGON_DIR = os.path.dirname(COOKBOOKS_DIR)                      # repo root
MODELS_DIR = os.path.join(ZYGON_DIR, "models")
PAPERS_DIR = os.path.join(ZYGON_DIR, "papers")

EXPECTED_MODELS = ["pypsa-eur", "pypsa-earth"]
# each model repo keeps its default config in a different place
CONFIG_REL = {
    "pypsa-eur": os.path.join("config", "config.default.yaml"),
    "pypsa-earth": "config.default.yaml",
}
DEFAULT_PYPSA_ENV = "/home/lukas/Desktop/earth/pypsa-earth/.pixi/envs/default"

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RUNGS = {"L0", "L1", "L2", "L3", "L4", "L5"}
LINENO_RE = re.compile(r"(:\d+\s*$|#L\d+)")

VERDICTS = {"turnkey", "assemble", "primitive-only", "absent"}
LIT_ROLES = {"defines", "extends", "canonical-use", "routine-use", "critiques"}
OVER = {"ensemble", "run"}
FORBIDDEN = ("asserts", "invalidates", "out_of_box")

REQUIRED_TOP = (
    "id", "title", "summary", "question", "aliases", "when_to_use", "family",
    "prevalence", "procedure", "variants", "literature", "topics", "models",
)


# ── helpers ─────────────────────────────────────────────────────────────────
def load(path):
    with open(path) as f:
        return yaml.safe_load(f)


def submodule_shas():
    """Read the live submodule SHAs so a moved submodule fails the book loudly."""
    out = {}
    try:
        res = subprocess.run(
            ["git", "submodule", "status"], cwd=ZYGON_DIR,
            capture_output=True, text=True, timeout=60, check=False,
        )
        for line in res.stdout.splitlines():
            parts = line.strip().lstrip("+-U ").split()
            if len(parts) >= 2:
                sha, path = parts[0], parts[1]
                out[os.path.basename(path)] = sha
    except (OSError, subprocess.TimeoutExpired):
        pass
    return out


def dotpath_exists(cfg, path):
    node = cfg
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True


def check_provenance(value, errors, label, root):
    """provenance = 'file:symbol' entries, ';'-separated. Each entry: the file exists
    under `root` and the symbol occurs verbatim in it. Ported from check_recipes.py,
    parameterised by root so each model section greps its own submodule."""
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
        fpath, symbol = fpath.strip(), symbol.strip()
        full = os.path.join(root, fpath)
        if not os.path.isfile(full):
            errors.append(f"{label}: provenance file missing ({fpath})")
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
        # compound symbols may use spaced separators: 'sym1 / sym2', 'a, b', 'a and b'
        for part in [p.strip() for p in re.split(r" / |, | and ", symbol) if p.strip()]:
            if part not in content:
                errors.append(f"{label}: symbol {part!r} not found verbatim in {fpath}")


def check_provenance_multi(value, errors, label, roots):
    """Pass if the provenance resolves against ANY of `roots`.

    Used for `procedure` and `assembly`, which may legitimately name a PyPSA LIBRARY
    symbol rather than a model-repo file: for a `primitive-only` method the assembly
    recipe IS "call optimize_mga from a driver", and there is no model-repo file to
    point at. `available` / `levers` / `where` stay strict (single model repo) because
    those are claims about that model's own config and code."""
    attempts = []
    for root in roots:
        errs = []
        check_provenance(value, errs, label, root)
        if not errs:
            return
        attempts.append((errs, root))
    if not attempts:
        return
    # Report the root that got FURTHEST (fewest complaints) — that is almost always the
    # one the author meant. Reporting the last root tried made a bad SYMBOL read as a
    # missing FILE, because the final root is the pypsa env where model paths never exist.
    errs, root = min(attempts, key=lambda a: len(a[0]))
    tried = ", ".join(os.path.basename(r.rstrip("/")) for _, r in attempts)
    errors.extend(f"{e} [closest root: {os.path.basename(root.rstrip('/'))}; "
                  f"tried: {tried}]" for e in errs)


def pypsa_env_info(env_path):
    """(site_packages_dir, version) for the pypsa install, or (None, None)."""
    pats = os.path.join(env_path, "lib", "python3*", "site-packages")
    for sp in sorted(glob.glob(pats)):
        if os.path.isdir(os.path.join(sp, "pypsa")):
            ver = None
            for di in glob.glob(os.path.join(sp, "pypsa-*.dist-info")):
                m = re.search(r"pypsa-([0-9][^/]*?)\.dist-info$", di)
                if m:
                    ver = m.group(1)
            return sp, ver
    return None, None


# ── per-file checks ─────────────────────────────────────────────────────────
def check_file(path, ctx):
    errors, warnings = [], []
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        doc = load(path)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"], []
    if not isinstance(doc, dict):
        return ["top level is not a mapping"], []

    # 14. forbidden fields (check first — a pasted recipe should fail on identity)
    for key in FORBIDDEN:
        if key in doc:
            errors.append(f"forbidden top-level field {key!r} — methods use "
                          f"`verifies`/`available` instead (see METHOD.schema.yaml)")

    # 1. required keys, id, slug. Only MISSING KEYS short-circuit (the checks below
    # would all raise on absent keys); a forbidden field must not mask the rest.
    missing = [k for k in REQUIRED_TOP if k not in doc]
    errors.extend(f"missing required key: {k}" for k in missing)
    if missing:
        return errors, warnings
    if doc["id"] != stem:
        errors.append(f"id {doc['id']!r} != filename stem {stem!r}")
    if not SLUG_RE.match(str(doc["id"])):
        errors.append(f"id not kebab-case: {doc['id']!r}")
    if doc["id"] not in ctx["slugs"]:
        errors.append(f"id {doc['id']!r} not in _qa/SLUGS.yaml")
    if doc.get("family") not in ctx["families"]:
        errors.append(f"family invalid: {doc.get('family')!r}")
    for key in ("aliases", "when_to_use"):
        if not isinstance(doc[key], list) or not doc[key]:
            errors.append(f"{key} must be a non-empty list")

    # 6. literature
    lit_papers = []
    for i, l in enumerate(doc["literature"] or []):
        label = f"literature[{i}]"
        for key in ("paper", "tier", "role", "note"):
            if key not in l:
                errors.append(f"{label}.{key} missing")
        paper = l.get("paper")
        lit_papers.append(paper)
        if l.get("role") not in LIT_ROLES:
            errors.append(f"{label}.role invalid: {l.get('role')!r}")
        if ctx["corpus"] is None:
            continue
        if paper not in ctx["corpus"]:
            errors.append(f"{label}.paper not found in papers/: {paper!r}")
        elif l.get("tier") != ctx["corpus"][paper]["tier"]:
            errors.append(f"{label}.tier {l.get('tier')!r} != actual tier "
                          f"{ctx['corpus'][paper]['tier']} (papers/{ctx['corpus'][paper]['dir']}/)")
    lit_set = set(lit_papers)

    # 12. prevalence arithmetic
    pv = doc["prevalence"] or {}
    for key in ("papers", "tier1", "tier2", "sweep_hits", "basis"):
        if key not in pv:
            errors.append(f"prevalence.{key} missing")
    if isinstance(pv.get("papers"), int) and pv["papers"] != len(lit_papers):
        errors.append(f"prevalence.papers {pv['papers']} != len(literature) {len(lit_papers)}")
    if all(isinstance(pv.get(k), int) for k in ("papers", "tier1", "tier2")):
        if pv["tier1"] + pv["tier2"] != pv["papers"]:
            errors.append(f"prevalence tier1+tier2 ({pv['tier1']}+{pv['tier2']}) "
                          f"!= papers ({pv['papers']})")

    # procedure: handle and provenance must agree about nullity
    for i, s in enumerate(doc["procedure"] or []):
        label = f"procedure[{i}]"
        if not s.get("step"):
            errors.append(f"{label}.step empty")
        if "handle" not in s or "provenance" not in s:
            errors.append(f"{label}: handle and provenance keys are both required (use null)")
            continue
        h, p = s.get("handle"), s.get("provenance")
        if (h is None) != (p is None):
            errors.append(f"{label}: handle and provenance must be null together "
                          f"(handle={h!r}, provenance={'set' if p else None})")
        if p is not None:
            check_provenance_multi(p, errors, label, ctx["any_root"])

    # 8/9. variants
    variant_ids = []
    for i, v in enumerate(doc["variants"] or []):
        label = f"variants[{i}]"
        vid = v.get("id")
        if not vid or not SLUG_RE.match(str(vid)):
            errors.append(f"{label}.id missing or not kebab-case: {vid!r}")
        else:
            variant_ids.append(vid)
        if not v.get("what"):
            errors.append(f"{label}.what empty")
        for p in v.get("papers") or []:
            if ctx["corpus"] is not None and p not in lit_set:
                errors.append(f"{label}.papers entry not in literature: {p!r}")
    if len(variant_ids) != len(set(variant_ids)):
        errors.append("variants[].id values are not unique")

    for i, p in enumerate(doc.get("pitfalls") or []):
        label = f"pitfalls[{i}]"
        for key in ("pitfall", "evidence", "note"):
            if key not in p:
                errors.append(f"{label}.{key} missing")
        if ctx["corpus"] is not None and p.get("evidence") not in lit_set:
            errors.append(f"{label}.evidence not in literature: {p.get('evidence')!r}")

    # 10. cross-references
    for field in ("requires_methods", "combines_with"):
        for s in doc.get(field) or []:
            if s == doc["id"]:
                errors.append(f"{field} references itself: {s!r}")
            elif s not in ctx["slugs"]:
                errors.append(f"{field} references unknown method slug: {s!r}")
    for t in doc.get("topics") or []:
        # topic cards live flat (v2) or under v1/ (pending migration)
        if not any(os.path.isfile(os.path.join(ctx["topics_dir"], sub, t + ".yaml"))
                   for sub in (".", "v1")):
            errors.append(f"topics references unknown topic card: {t!r}")

    # 11. pypsa_primitive
    prim = doc.get("pypsa_primitive")
    if prim:
        for key in ("symbol", "pypsa_version", "exposed_by", "reachable_via", "note"):
            if key not in prim:
                errors.append(f"pypsa_primitive.{key} missing")
        if ctx["pypsa_sp"] is None:
            warnings.append("pypsa env not found — pypsa_primitive.symbol unverified "
                            "(set PYPSA_ENV to check)")
        else:
            check_provenance(prim.get("symbol", ""), errors, "pypsa_primitive",
                             ctx["pypsa_sp"])
            if ctx["pypsa_ver"] and str(prim.get("pypsa_version")) != ctx["pypsa_ver"]:
                errors.append(f"pypsa_primitive.pypsa_version {prim.get('pypsa_version')!r} "
                              f"!= installed {ctx['pypsa_ver']!r}")

    # 2-5, 7, 13. model sections
    models = doc["models"]
    if not isinstance(models, list) or len(models) != 2:
        errors.append("models must be a list with exactly two entries "
                      "(pypsa-eur and pypsa-earth; use not_applicable, never omission)")
        return errors, warnings
    got = [m.get("model") for m in models]
    if got != EXPECTED_MODELS:
        errors.append(f"models must be {EXPECTED_MODELS} in that order, got {got}")

    ladder_variants = set()
    for m in models:
        name = m.get("model")
        if name not in EXPECTED_MODELS:
            continue
        ml = f"models[{name}]"
        root = ctx["repo"][name]
        va = m.get("version_anchor") or {}
        live = ctx["shas"].get(name)
        ref = str(va.get("ref", ""))
        if live and not ref:
            errors.append(f"{ml}.version_anchor.ref missing (submodule is at {live[:8]})")
        elif live and not live.startswith(ref[:8]):
            errors.append(f"{ml}.version_anchor.ref {ref[:8]} != live submodule "
                          f"{live[:8]} — re-verify claims and restamp")
        if "date" not in va:
            errors.append(f"{ml}.version_anchor.date missing")

        if m.get("not_applicable"):
            continue

        # functionality ids
        reg = ctx["registry"][name]
        cited, cited_absent = [], []
        for i, fn in enumerate(m.get("functionality") or []):
            fid = fn.get("id")
            if fid not in reg:
                errors.append(f"{ml}.functionality[{i}].id not in "
                              f"cookbooks/{name}/topics/FUNCTIONALITY.yaml: {fid!r}")
            else:
                cited.append(fid)
                if reg[fid] == "absent":
                    cited_absent.append(fid)
            if not fn.get("role"):
                errors.append(f"{ml}.functionality[{i}].role empty")

        av = m.get("available") or {}
        for key in ("verdict", "how", "missing", "provenance"):
            if key not in av:
                errors.append(f"{ml}.available.{key} missing")
        if av.get("verdict") not in VERDICTS:
            errors.append(f"{ml}.available.verdict invalid: {av.get('verdict')!r}")
        if "provenance" in av:
            check_provenance(av["provenance"], errors, f"{ml}.available", root)
        # Only a real contradiction warrants a warning: claiming turnkey while EVERY
        # capability the card rests on is absent. Citing one absent id among working
        # ones is the intended way to say "and here is why the nearest thing is not
        # this" — the schema asks for those citations, so they must not be noise.
        if av.get("verdict") == "turnkey" and cited and len(cited_absent) == len(cited):
            warnings.append(f"{ml}: verdict 'turnkey' but every capability cited is "
                            f"absent from the registry: {cited_absent}")
        # NOTE: deliberately NOT warning on `verdict: absent` with levers listed. An
        # absent method still has keys that decide what it would be applied to, what
        # it would cost, and which substitute exists — see the `levers` note in
        # METHOD.schema.yaml. The verdict is the only field that claims availability.

        cfg = ctx["config"][name]
        for i, lever in enumerate(m.get("levers") or []):
            label = f"{ml}.levers[{i}]"
            for key in ("key", "effect", "default", "provenance"):
                if key not in lever:
                    errors.append(f"{label}.{key} missing")
            if "key" in lever and cfg is not None and not dotpath_exists(cfg, str(lever["key"])):
                errors.append(f"{label}.key not found in {CONFIG_REL[name]}: {lever['key']!r}")
            if "provenance" in lever:
                check_provenance(lever["provenance"], errors, label, root)

        for i, a in enumerate(m.get("assembly") or []):
            label = f"{ml}.assembly[{i}]"
            if not a.get("step"):
                errors.append(f"{label}.step empty")
            for key in ("config", "code", "provenance"):
                if key not in a:
                    errors.append(f"{label}.{key} key required (use null)")
            for u in a.get("uses") or []:
                if u not in reg:
                    errors.append(f"{label}.uses id not in {name} FUNCTIONALITY.yaml: {u!r}")
            if a.get("provenance"):
                # may name a library primitive — see check_provenance_multi
                check_provenance_multi(a["provenance"], errors, label,
                                       [root] + ([ctx["pypsa_sp"]] if ctx["pypsa_sp"] else []))

        max_rung, has_l3 = -1, False
        for i, b in enumerate(m.get("boundary") or []):
            label = f"{ml}.boundary[{i}]"
            rung = b.get("rung")
            if rung not in RUNGS:
                errors.append(f"{label}.rung invalid: {rung!r}")
            else:
                max_rung = max(max_rung, int(rung[1]))
                has_l3 = has_l3 or rung == "L3"
            v = b.get("variant")
            if v not in variant_ids:
                errors.append(f"{label}.variant {v!r} does not join any variants[].id")
            else:
                ladder_variants.add(v)
            if not b.get("note"):
                errors.append(f"{label}.note empty")
        if not m.get("boundary"):
            errors.append(f"{ml}.boundary missing — every model section needs a ladder")
        if max_rung >= 2 and not m.get("where"):
            errors.append(f"{ml}: boundary has rungs >= L2 but `where` is missing")
        if has_l3 and not m.get("data_dependencies"):
            errors.append(f"{ml}: boundary has an L3 rung but `data_dependencies` is missing")
        for i, w in enumerate(m.get("where") or []):
            label = f"{ml}.where[{i}]"
            for key in ("change", "anchor", "provenance"):
                if key not in w:
                    errors.append(f"{label}.{key} missing")
            if "provenance" in w:
                check_provenance(w["provenance"], errors, label, root)
        for i, d in enumerate(m.get("data_dependencies") or []):
            for key in ("input", "required_for", "availability"):
                if key not in d:
                    errors.append(f"{ml}.data_dependencies[{i}].{key} missing")

        cp = m.get("cost_profile")
        if cp:
            for key in ("solves", "relative", "note"):
                if key not in cp:
                    errors.append(f"{ml}.cost_profile.{key} missing")
        for i, vf in enumerate(m.get("verifies") or []):
            label = f"{ml}.verifies[{i}]"
            if vf.get("variant") not in variant_ids:
                errors.append(f"{label}.variant does not join variants[].id: "
                              f"{vf.get('variant')!r}")
            if vf.get("over") not in OVER:
                errors.append(f"{label}.over invalid: {vf.get('over')!r}")
            for key in ("check", "note"):
                if not vf.get(key):
                    errors.append(f"{label}.{key} empty")
        for key in FORBIDDEN:
            if key in m:
                errors.append(f"{ml}: forbidden field {key!r} — use `verifies`/`available`")

    # 8b. every variant must appear on at least one model's ladder
    for v in variant_ids:
        if v not in ladder_variants:
            warnings.append(f"variants[{v}] appears on no model's boundary ladder")

    return errors, warnings


def detect_cycles(graph):
    """requires_methods must be a DAG."""
    cycles, state = [], {}

    def walk(n, stack):
        if state.get(n) == 1:
            cycles.append(" -> ".join(stack[stack.index(n):] + [n]))
            return
        if state.get(n) == 2:
            return
        state[n] = 1
        for nxt in graph.get(n, []):
            if nxt in graph:
                walk(nxt, stack + [nxt])
        state[n] = 2

    for n in sorted(graph):
        walk(n, [n])
    return cycles


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="restrict to these slugs")
    ap.add_argument("--no-warnings", action="store_true")
    args = ap.parse_args()

    slugdoc = load(os.path.join(QA_DIR, "SLUGS.yaml"))
    corpus_path = os.path.join(QA_DIR, "CORPUS.yaml")
    corpus = load(corpus_path) if os.path.isfile(corpus_path) else None
    if corpus is None or not os.path.isdir(PAPERS_DIR):
        print("WARNING: papers/ or CORPUS.yaml absent (papers/ is gitignored) — "
              "literature[].paper unverified. Run sweep_corpus.py to enable.",
              file=sys.stderr)
        corpus = None

    env_path = os.environ.get("PYPSA_ENV", DEFAULT_PYPSA_ENV)
    pypsa_sp, pypsa_ver = pypsa_env_info(env_path)

    ctx = {
        "slugs": {m["id"] for m in slugdoc["methods"]},
        "families": set(slugdoc["families"]),
        "corpus": corpus,
        "shas": submodule_shas(),
        "repo": {m: os.path.join(MODELS_DIR, m) for m in EXPECTED_MODELS},
        "topics_dir": os.path.join(COOKBOOKS_DIR, "pypsa-eur", "topics"),
        "pypsa_sp": pypsa_sp,
        "pypsa_ver": pypsa_ver,
        "config": {},
        "registry": {},
    }
    # roots a `procedure` step may resolve against: either model, or the library
    ctx["any_root"] = [ctx["repo"][m] for m in EXPECTED_MODELS] + (
        [pypsa_sp] if pypsa_sp else []
    )
    for m in EXPECTED_MODELS:
        cpath = os.path.join(ctx["repo"][m], CONFIG_REL[m])
        ctx["config"][m] = load(cpath) if os.path.isfile(cpath) else None
        if ctx["config"][m] is None:
            print(f"WARNING: {m} config not found at {cpath} — levers[].key unverified",
                  file=sys.stderr)
        fpath = os.path.join(COOKBOOKS_DIR, m, "topics", "FUNCTIONALITY.yaml")
        entries = load(fpath) if os.path.isfile(fpath) else []
        ctx["registry"][m] = {e["id"]: e.get("status") for e in (entries or [])}

    # unconverted v1 essays live in v1/; flat .yaml files are v2 exec specs
    files = sorted(f for f in os.listdir(BOOK_DIR) if f.endswith(".yaml")
                   and f != "TEMPLATE.yaml")
    v1_dir = os.path.join(BOOK_DIR, "v1")
    if os.path.isdir(v1_dir):
        files += sorted(os.path.join("v1", f) for f in os.listdir(v1_dir)
                        if f.endswith(".yaml"))
    if args.only:
        files = [f for f in files
                 if os.path.splitext(os.path.basename(f))[0] in set(args.only)]
    # v2 exec specs (schema_version: 2) are validated by check_method_exec.py
    # — this checker owns only the unconverted v1 essays
    v1_files = []
    for f in files:
        try:
            doc = load(os.path.join(BOOK_DIR, f))
        except yaml.YAMLError:
            v1_files.append(f)
            continue
        if not (isinstance(doc, dict) and doc.get("schema_version") == 2):
            v1_files.append(f)
    if len(files) != len(v1_files):
        print(f"({len(files) - len(v1_files)} v2 exec spec(s) skipped — "
              "checked by check_method_exec.py)")
    files = v1_files
    if not files:
        print("no method cards found — nothing to check")
        sys.exit(0)

    n_fail, n_warn, graph = 0, 0, {}
    for fname in files:
        path = os.path.join(BOOK_DIR, fname)
        errors, warnings = check_file(path, ctx)
        if os.sep not in fname:
            errors.append("v1 essay filed flat — move it to v1/")
        try:
            doc = load(path)
            if isinstance(doc, dict) and doc.get("id"):
                graph[doc["id"]] = list(doc.get("requires_methods") or [])
        except yaml.YAMLError:
            pass
        if errors:
            n_fail += 1
            print(f"FAIL  {fname}")
            for e in errors:
                print(f"      - {e}")
        else:
            print(f"ok    {fname}")
        if warnings and not args.no_warnings:
            n_warn += len(warnings)
            for w in warnings:
                print(f"      ! {w}")

    cycles = detect_cycles(graph)
    for cyc in cycles:
        print(f"FAIL  requires_methods cycle: {cyc}")

    print(f"\n{len(files) - n_fail}/{len(files)} method cards pass"
          + (f", {len(cycles)} requires_methods cycles" if cycles else "")
          + (f", {n_warn} warnings" if n_warn else ""))
    n_fail += len(cycles)
    if pypsa_sp is None:
        print(f"note: pypsa env not found at {env_path} (set PYPSA_ENV)")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
