#!/usr/bin/env python3
"""Restructure the knowledge base into the flat, model-merged layout.

One-shot migration from the ``cookbooks/<model>/<book>`` layout (topic cards
duplicated per model, a ``v1/`` shelf beside the migrated ones, methods with a
per-model ``status``) to::

    topics/<slug>.yaml            one card, models[] carries the per-model part
    recipes/<book>/<slug>.yaml    eur and earth books merged per slug
    methods/                      only the specs the topic cards cite, no status
    data_quality/<model>/         scorecards, unchanged content
    baselines/<model>/            was fixtures/recipes/baseline-<model>
    policy/                       was data/energy_brockhaus
    basemaps/  models/            unchanged
    archive/                      everything else, old path preserved; the app
                                  never reads it

Run from the repo root with PyYAML available::

    python3 archive/tools/restructure.py --dry-run   # plan + warnings, no writes
    python3 archive/tools/restructure.py             # the move
    python3 archive/tools/restructure.py --validate  # re-check a checkout later

``--validate`` is the part worth keeping: it resolves every reference a topic
card makes and is the replacement for the archived ``_qa`` checkers.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]

MODELS = ("pypsa-eur", "pypsa-earth")
ANCHORS = {
    "pypsa-eur": "849c8858d2536ccf8eed0c2e838d22a474a7ee5d",
    "pypsa-earth": "8435f4c8cc05f30088933b37b7db497ff860dc53",
}
BOOKS = ("generation_conversion", "demand")
EXPECTED_HEAD = "ffb1d8e2bb6fff5790ba1469688d237e8ce13b4b"

MERGED_TOPICS = (
    "asset-cost-benefit",
    "capacity-expansion",
    "locational-electricity-markets",
    "marginal-price-prediction",
)

# The three topics stubbed at migration. Question and
# when_to_use descend from the v1 cards named in `sources`; a drafted
# question replaces the v1 one where several cards are fused.
STUBS: dict[str, dict[str, Any]] = {
    "transmission-planning": {
        "title": "Transmission planning",
        "sources": ["transmission-expansion-planning"],
        "question": None,
    },
    "storage-dispatch": {
        "title": "Storage dispatch",
        "sources": [
            "battery-storage-sizing",
            "long-duration-storage-ldes",
            "storage-revenue-stacking",
        ],
        "question": (
            "How much storage does the system need, of what duration and where, "
            "how is it dispatched against prices and constraints, and what does "
            "it earn across arbitrage, capacity and ancillary revenues? Sizing "
            "for planners, dispatch and the business case for developers and "
            "investors, from grid batteries to seasonal hydrogen."
        ),
    },
    "clean-procurement": {
        "title": "Clean procurement",
        # v1 TOPIC slugs only: build_stub resolves each through repo.v1_doc for
        # both models. The card's real ancestor, the method essay
        # additionality-and-24-7-matching (archive/cookbooks/methods/v1/), is
        # not a topic and cannot be listed here; the live card is hand-written
        # and supersedes anything build_stub would emit.
        "sources": ["data-center-load-growth", "electrolyser-grid-flexibility"],
        "question": (
            "How can a large electricity consumer — a data centre, a hyperscale "
            "campus, a C&I site, an electrolyser — procure clean electricity, "
            "what does each procurement rule cost, and what does it build? The "
            "canonical comparison: how much more expensive is it to run a data "
            "centre on hourly-matched 98%-clean electricity than on an "
            "annual-matched 100% renewable PPA, and which mix of wind, solar, "
            "batteries, long-duration storage and clean firm capacity does each "
            "rule buy. The RFNBO hourly-matching rule for green hydrogen is the "
            "sibling case — the same constraint algebra at a different grouping, "
            "and the only one either model ships machinery for."
        ),
    },
}

TOPIC_SLUGS = MERGED_TOPICS + tuple(STUBS)

SECTION_KEYS = (
    "coverage",
    "gap_assessment",
    "recipes",
    "methods",
    "defaults",
    "plots",
    "version_anchor",
)

# Paths that move under archive/ with their old relative path. Missing ones
# are skipped; the "nothing tracked remains" assertion at the end catches
# anything this list forgot.
ARCHIVE_PATHS = [
    "cookbooks/_qa",
    "cookbooks/methods/_qa",
    "cookbooks/methods/v1",
    "cookbooks/methods/INDEX.md",
    "cookbooks/methods/README.md",
    "cookbooks/methods/PREVALENCE.md",
    "cookbooks/methods/PRIMITIVES.md",
    "cookbooks/methods/TEMPLATE.yaml",
    "cookbooks/methods/fixing-heat-load-factor.yaml",
    "cookbooks/pypsa-eur/README.md",
    "cookbooks/pypsa-earth/README.md",
    "cookbooks/pypsa-earth/PYPSA_EUR_COVERAGE.md",
    "cookbooks/pypsa-earth/_qa",
    "fixtures/BASELINE.md",
    "fixtures/networks",
] + [
    f"cookbooks/{m}/{book}/{name}"
    for m in MODELS
    for book, names in {
        "topics": ("INDEX.md", "README.md", "FUNCTIONALITY.yaml", "_qa", "v1"),
        "generation_conversion": ("INDEX.md", "VALIDATION.md", "_qa"),
        "demand": ("INDEX.md", "VALIDATION.md", "_qa"),
        "data_quality": ("maps", "_qa"),
    }.items()
    for name in names
]

DATA_QUALITY_LIVE = ("countries", "datasets.yaml", "MATRIX.csv", "INDEX.md", "README.md")

TOP_LEVEL = {
    ".gitignore",
    ".gitmodules",
    "README.md",
    "archive",
    "baselines",
    "basemaps",
    "data_quality",
    "methods",
    "models",
    "policy",
    "recipes",
    "topics",
}


# --------------------------------------------------------------------------
# helpers


class Dumper(yaml.SafeDumper):
    """Block style, insertion order, folded scalars for prose."""


def _str_representer(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = None
    if "\n" in value:
        style = "|"
    elif len(value) > 80:
        style = ">"
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


Dumper.add_representer(str, _str_representer)


def dump(doc: Any) -> str:
    return yaml.dump(
        doc, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=80
    )


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout


def union(*lists: list[str]) -> list[str]:
    out: list[str] = []
    for items in lists:
        for item in items or []:
            if item not in out:
                out.append(item)
    return out


def section_of(doc: dict[str, Any], model: str) -> dict[str, Any] | None:
    for entry in doc.get("models") or []:
        if isinstance(entry, dict) and entry.get("model") == model:
            return entry
    return None


def models_of(doc: dict[str, Any]) -> set[str]:
    return {
        e["model"] for e in doc.get("models") or [] if isinstance(e, dict) and "model" in e
    }


class Warnings(list[str]):
    def add(self, msg: str) -> None:
        self.append(msg)


# --------------------------------------------------------------------------
# loading


class Repo:
    def __init__(self) -> None:
        cb = ROOT / "cookbooks"
        self.recipe_text: dict[tuple[str, str, str], str] = {}
        self.recipe_doc: dict[tuple[str, str, str], dict[str, Any]] = {}
        for m in MODELS:
            for book in BOOKS:
                for path in sorted((cb / m / book).glob("*.yaml")):
                    text = path.read_text(encoding="utf-8")
                    self.recipe_text[m, book, path.stem] = text
                    self.recipe_doc[m, book, path.stem] = yaml.safe_load(text)
        self.topic_doc: dict[tuple[str, str], dict[str, Any]] = {}
        self.v1_doc: dict[tuple[str, str], dict[str, Any]] = {}
        for m in MODELS:
            for path in sorted((cb / m / "topics").glob("*.yaml")):
                if path.name == "FUNCTIONALITY.yaml":
                    continue
                self.topic_doc[m, path.stem] = read_yaml(path)
            for path in sorted((cb / m / "topics" / "v1").glob("*.yaml")):
                self.v1_doc[m, path.stem] = read_yaml(path)
        self.method_path: dict[str, Path] = {}
        for path in sorted((cb / "methods").glob("*.yaml")):
            doc = read_yaml(path)
            if isinstance(doc, dict) and doc.get("id") and doc["id"] != "CHANGE-ME":
                self.method_path[path.stem] = path
        for spec in sorted((cb / "methods").glob("*/spec.yaml")):
            self.method_path[spec.parent.name] = spec
        self.method_doc = {k: read_yaml(p) for k, p in self.method_path.items()}

    def recipe_slugs(self, book: str) -> dict[str, set[str]]:
        """slug -> models that have a file for it in `book`."""
        out: dict[str, set[str]] = {}
        for m, b, slug in self.recipe_doc:
            if b == book:
                out.setdefault(slug, set()).add(m)
        return out


# --------------------------------------------------------------------------
# merges


def merge_recipe(
    slug: str, eur_text: str, earth_text: str, warnings: Warnings
) -> tuple[str, dict[str, Any]]:
    """Splice the earth model section into the eur file; when_to_use as a union."""
    eur = yaml.safe_load(eur_text)
    earth = yaml.safe_load(earth_text)
    for key in ("title", "summary"):
        if eur.get(key) != earth.get(key):
            warnings.add(f"recipe {slug}: {key} differs, taking eur")
    expected = dict(eur)
    expected["when_to_use"] = union(eur.get("when_to_use") or [], earth.get("when_to_use") or [])
    expected["models"] = list(eur["models"]) + list(earth["models"])

    eur_lines = eur_text.rstrip("\n").split("\n")
    earth_lines = earth_text.rstrip("\n").split("\n")
    models_at = next(i for i, ln in enumerate(eur_lines) if ln == "models:")
    earth_at = next(
        i for i, ln in enumerate(earth_lines) if ln.startswith("  - model: pypsa-earth")
    )
    extras = [
        "  - " + json.dumps(item, ensure_ascii=False)
        for item in expected["when_to_use"]
        if item not in (eur.get("when_to_use") or [])
    ]
    insert_at = models_at
    while insert_at > 0 and not eur_lines[insert_at - 1].strip():
        insert_at -= 1
    merged = (
        eur_lines[:insert_at] + extras + eur_lines[insert_at:] + earth_lines[earth_at:]
    )
    text = "\n".join(merged) + "\n"
    if yaml.safe_load(text) != expected:
        warnings.add(f"recipe {slug}: splice did not round-trip, dumped instead")
        text = dump(expected)
    return text, expected


def check_demand(slug: str, eur: dict[str, Any], earth: dict[str, Any]) -> None:
    """The demand books are dual copies; the eur file wins and must equal earth."""
    fixed = json.loads(json.dumps(earth))
    sec = section_of(fixed, "pypsa-eur")
    ref = section_of(eur, "pypsa-eur")
    if sec is not None and ref is not None:
        sec["version_anchor"] = ref["version_anchor"]
    if fixed != eur:
        msg = f"demand {slug}: eur and earth copies differ beyond the eur anchor"
        raise SystemExit(msg)


def method_verified(doc: dict[str, Any], model: str) -> bool:
    sec = section_of(doc, model)
    return sec is not None and sec.get("status") == "verified"


def topic_section(card: dict[str, Any], model: str) -> dict[str, Any]:
    out: dict[str, Any] = {"model": model}
    for key in SECTION_KEYS:
        if key == "version_anchor":
            out[key] = section_of(card, model)["version_anchor"]
        elif key == "plots":
            if card.get("plots"):
                out[key] = card["plots"]
        else:
            value = card.get(key)
            out[key] = value.strip() if isinstance(value, str) else (value or [])
    return out


def assemble_topic(
    slug: str, repo: Repo, warnings: Warnings
) -> dict[str, Any]:
    eur = repo.topic_doc["pypsa-eur", slug]
    earth = repo.topic_doc["pypsa-earth", slug]
    if eur.get("question") != earth.get("question"):
        warnings.add(f"topic {slug}: question differs, taking eur")
    doc: dict[str, Any] = {
        "id": eur["id"],
        "title": eur["title"],
        "question": eur["question"],
        "when_to_use": union(eur.get("when_to_use") or [], earth.get("when_to_use") or []),
        "models": [],
    }
    for model, card in (("pypsa-eur", eur), ("pypsa-earth", earth)):
        sec = topic_section(card, model)
        kept = []
        for m in sec["methods"]:
            spec = repo.method_doc.get(m["id"])
            if spec is None or not method_verified(spec, model):
                warnings.add(f"topic {slug}/{model}: dropping method {m['id']} (not verified)")
                continue
            kept.append(m)
        sec["methods"] = kept
        doc["models"].append(sec)
    return doc


def build_stub(
    slug: str,
    repo: Repo,
    recipe_models: dict[tuple[str, str], set[str]],
    date: str,
) -> dict[str, Any]:
    spec = STUBS[slug]
    sources = spec["sources"]
    v1_eur = [repo.v1_doc["pypsa-eur", s] for s in sources]
    v1_earth = [repo.v1_doc["pypsa-earth", s] for s in sources]
    question = spec["question"] or v1_eur[0]["question"]
    doc: dict[str, Any] = {
        "id": slug,
        "title": spec["title"],
        "question": question.strip(),
        "when_to_use": union(
            *[c.get("when_to_use") or [] for c in v1_eur],
            *[c.get("when_to_use") or [] for c in v1_earth],
        ),
        "models": [],
    }
    archived = ", ".join(sources)
    for model, cards in (("pypsa-eur", v1_eur), ("pypsa-earth", v1_earth)):
        recipes = {}
        for book in BOOKS:
            wanted = union(*[(c.get("recipes") or {}).get(book) or [] for c in cards])
            recipes[book] = [s for s in wanted if model in recipe_models.get((book, s), set())]
        doc["models"].append(
            {
                "model": model,
                "coverage": "gap",
                "gap_assessment": (
                    f"No executable method is wired for {model} yet. This card "
                    f"descends from the v1 cards {archived} (archived under "
                    f"archive/cookbooks/{model}/topics/v1/); the recipes below "
                    "are the parts of those cards whose recipe pages exist in "
                    "the merged book with a section for this model. Until a "
                    f"method spec is verified for {model}, the assistant can "
                    "describe levers but cannot scope a study."
                ),
                "recipes": recipes,
                "methods": [],
                "defaults": [],
                "version_anchor": {"ref": ANCHORS[model], "date": date},
            }
        )
    return doc


TOP_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")


def edit_method(text: str, keep: set[str]) -> tuple[str, dict[str, Any]]:
    """Drop schema_version, every status line, and model entries not in `keep`."""
    lines = text.rstrip("\n").split("\n")
    doc = yaml.safe_load(text)
    entry_models = [e.get("model") for e in doc.get("models") or []]
    starts = [i for i, ln in enumerate(lines) if ln.startswith("- model: ")]
    if len(starts) != len(entry_models):
        msg = "method text and parse disagree on the number of model entries"
        raise SystemExit(msg)
    drop: set[int] = set()
    for idx, (start, model) in enumerate(zip(starts, entry_models, strict=True)):
        if model in keep:
            continue
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith("- model: ") or TOP_KEY.match(lines[j]):
                end = j
                break
        drop.update(range(start, end))
    out = [
        ln
        for i, ln in enumerate(lines)
        if i not in drop
        and not ln.startswith("schema_version:")
        and not ln.startswith("  status:")
    ]
    new_text = "\n".join(out) + "\n"
    expected = {k: v for k, v in doc.items() if k != "schema_version"}
    expected["models"] = [
        {k: v for k, v in e.items() if k != "status"}
        for e in doc.get("models") or []
        if e.get("model") in keep
    ]
    if yaml.safe_load(new_text) != expected:
        msg = f"method {doc.get('id')}: text edit did not round-trip"
        raise SystemExit(msg)
    return new_text, expected


# --------------------------------------------------------------------------
# validation (shared by the in-memory pass, the on-disk pass and --validate)


def validate(
    topics: dict[str, dict[str, Any]],
    recipe_models: dict[tuple[str, str], set[str]],
    method_models: dict[str, set[str]],
) -> list[str]:
    errors: list[str] = []
    if set(topics) != set(TOPIC_SLUGS):
        errors.append(f"topics are {sorted(topics)}, expected {sorted(TOPIC_SLUGS)}")
    cited: set[str] = set()
    for slug, doc in topics.items():
        for key in ("schema_version", "rank"):
            if key in doc:
                errors.append(f"topic {slug}: carries {key}")
        if doc.get("id") != slug:
            errors.append(f"topic {slug}: id is {doc.get('id')!r}")
        seen: set[str] = set()
        for sec in doc.get("models") or []:
            model = sec.get("model")
            if model in seen:
                errors.append(f"topic {slug}: duplicate section for {model}")
            seen.add(model)
            if model not in MODELS:
                errors.append(f"topic {slug}: unknown model {model!r}")
                continue
            if sec.get("coverage") not in ("ready", "partial", "gap"):
                errors.append(f"topic {slug}/{model}: coverage {sec.get('coverage')!r}")
            if (sec.get("version_anchor") or {}).get("ref") != ANCHORS[model]:
                errors.append(f"topic {slug}/{model}: version_anchor is not the canonical ref")
            for book in BOOKS:
                for rslug in (sec.get("recipes") or {}).get(book) or []:
                    if model not in recipe_models.get((book, rslug), set()):
                        errors.append(
                            f"topic {slug}/{model}: recipe {book}/{rslug} has no section for {model}"
                        )
            for m in sec.get("methods") or []:
                cited.add(m["id"])
                if model not in method_models.get(m["id"], set()):
                    errors.append(
                        f"topic {slug}/{model}: method {m['id']} has no section for {model}"
                    )
    for mid in method_models:
        if mid not in cited:
            errors.append(f"method {mid}: not cited by any topic")
    return errors


def scan_disk() -> tuple[
    dict[str, dict[str, Any]],
    dict[tuple[str, str], set[str]],
    dict[str, set[str]],
    list[str],
]:
    errors: list[str] = []
    topics = {p.stem: read_yaml(p) for p in sorted((ROOT / "topics").glob("*.yaml"))}
    recipe_models: dict[tuple[str, str], set[str]] = {}
    for book in BOOKS:
        for p in sorted((ROOT / "recipes" / book).glob("*.yaml")):
            doc = read_yaml(p)
            if doc.get("id") != p.stem:
                errors.append(f"recipe {book}/{p.name}: id is {doc.get('id')!r}")
            recipe_models[book, p.stem] = models_of(doc)
    method_models: dict[str, set[str]] = {}
    for p in sorted((ROOT / "methods").glob("*.yaml")):
        method_models[p.stem] = models_of(read_yaml(p))
    for p in sorted((ROOT / "methods").glob("*/spec.yaml")):
        method_models[p.parent.name] = models_of(read_yaml(p))
    for p in ROOT.rglob("*.yaml"):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in ("archive", "models", ".git"):
            continue
        text = p.read_text(encoding="utf-8")
        if re.search(r"^schema_version:", text, re.M):
            errors.append(f"{rel}: carries schema_version")
        if rel.parts[0] == "methods" and re.search(r"^  status:", text, re.M):
            errors.append(f"{rel}: carries a status line")
    tracked_top = {ln.split("/")[0] for ln in git("ls-files").split("\n") if ln}
    if tracked_top != TOP_LEVEL:
        errors.append(f"top level is {sorted(tracked_top)}, expected {sorted(TOP_LEVEL)}")
    return topics, recipe_models, method_models, errors


# --------------------------------------------------------------------------
# the plan


class Plan:
    def __init__(self, repo: Repo, date: str) -> None:
        self.warnings = Warnings()
        self.moves: list[tuple[str, str]] = []
        self.removes: list[str] = []
        self.writes: dict[str, str] = {}
        self.symlinks: dict[str, str] = {}
        self.topics: dict[str, dict[str, Any]] = {}
        self.recipe_models: dict[tuple[str, str], set[str]] = {}
        self.method_models: dict[str, set[str]] = {}

        for src in ARCHIVE_PATHS:
            if (ROOT / src).exists():
                self.moves.append((src, f"archive/{src}"))

        # recipes
        for book in BOOKS:
            slugs = repo.recipe_slugs(book)
            for slug, models in sorted(slugs.items()):
                dst = f"recipes/{book}/{slug}.yaml"
                eur_key = ("pypsa-eur", book, slug)
                earth_key = ("pypsa-earth", book, slug)
                if models == {"pypsa-eur"}:
                    self.moves.append((f"cookbooks/pypsa-eur/{book}/{slug}.yaml", dst))
                    self.recipe_models[book, slug] = models_of(repo.recipe_doc[eur_key])
                elif models == {"pypsa-earth"}:
                    self.moves.append((f"cookbooks/pypsa-earth/{book}/{slug}.yaml", dst))
                    self.recipe_models[book, slug] = models_of(repo.recipe_doc[earth_key])
                elif book == "demand":
                    check_demand(slug, repo.recipe_doc[eur_key], repo.recipe_doc[earth_key])
                    self.moves.append((f"cookbooks/pypsa-eur/{book}/{slug}.yaml", dst))
                    self.removes.append(f"cookbooks/pypsa-earth/{book}/{slug}.yaml")
                    self.recipe_models[book, slug] = models_of(repo.recipe_doc[eur_key])
                else:
                    text, doc = merge_recipe(
                        slug, repo.recipe_text[eur_key], repo.recipe_text[earth_key], self.warnings
                    )
                    self.moves.append((f"cookbooks/pypsa-eur/{book}/{slug}.yaml", dst))
                    self.removes.append(f"cookbooks/pypsa-earth/{book}/{slug}.yaml")
                    self.writes[dst] = text
                    self.recipe_models[book, slug] = models_of(doc)

        # topics
        for slug in MERGED_TOPICS:
            doc = assemble_topic(slug, repo, self.warnings)
            self.moves.append((f"cookbooks/pypsa-eur/topics/{slug}.yaml", f"topics/{slug}.yaml"))
            self.removes.append(f"cookbooks/pypsa-earth/topics/{slug}.yaml")
            self.writes[f"topics/{slug}.yaml"] = dump(doc)
            self.topics[slug] = doc
        for slug in STUBS:
            doc = build_stub(slug, repo, self.recipe_models, date)
            self.writes[f"topics/{slug}.yaml"] = dump(doc)
            self.topics[slug] = doc

        # methods: only what the merged cards cite, verified sections only
        cited: dict[str, set[str]] = {}
        for doc in self.topics.values():
            for sec in doc["models"]:
                for m in sec["methods"]:
                    cited.setdefault(m["id"], set()).add(sec["model"])
        for mid in sorted(cited):
            path = repo.method_path[mid]
            rel = path.relative_to(ROOT)
            keep = {m for m in MODELS if method_verified(repo.method_doc[mid], m)}
            text, doc = edit_method(path.read_text(encoding="utf-8"), keep)
            if rel.name == "spec.yaml":
                self.moves.append((str(rel.parent), f"methods/{mid}"))
                dst = f"methods/{mid}/spec.yaml"
            else:
                self.moves.append((str(rel), f"methods/{mid}.yaml"))
                dst = f"methods/{mid}.yaml"
            self.writes[dst] = text
            self.method_models[mid] = models_of(doc)

        # data quality, baselines, policy
        for m in MODELS:
            for name in DATA_QUALITY_LIVE:
                src = f"cookbooks/{m}/data_quality/{name}"
                if (ROOT / src).exists():
                    self.moves.append((src, f"data_quality/{m}/{name}"))
            self.moves.append((f"fixtures/recipes/baseline-{m}", f"baselines/{m}"))
        self.moves.append(("data/energy_brockhaus", "policy"))

        # symlinks one level deeper under archive/
        for link in sorted((ROOT / "fixtures" / "networks").iterdir()):
            if link.is_symlink():
                self.symlinks[f"archive/fixtures/networks/{link.name}"] = "../" + os.readlink(link)

        # text touch-ups
        self.writes[".gitignore"] = (
            "__pycache__/\narchive/cookbooks/methods/_qa/text/\npolicy/_work/bundles/\n"
        )
        for m in MODELS:
            for name in ("manifest.yaml", "config.yaml"):
                src = ROOT / "fixtures" / "recipes" / f"baseline-{m}" / name
                if not src.exists():
                    continue
                text = src.read_text(encoding="utf-8")
                new = text
                for mm in MODELS:
                    new = new.replace(f"fixtures/recipes/baseline-{mm}/", f"baselines/{mm}/")
                new = new.replace("fixtures/BASELINE.md", "archive/fixtures/BASELINE.md")
                if new != text:
                    self.writes[f"baselines/{m}/{name}"] = new
        self.writes["README.md"] = README

        self.errors = validate(self.topics, self.recipe_models, self.method_models)

    def report(self) -> None:
        print(f"moves: {len(self.moves)}  removes: {len(self.removes)}  writes: {len(self.writes)}")
        print(f"topics: {sorted(self.topics)}")
        print(f"methods kept: {sorted(self.method_models)}")
        for w in self.warnings:
            print("WARN", w)
        for e in self.errors:
            print("ERROR", e)

    def apply(self) -> None:
        for src, dst in self.moves:
            (ROOT / dst).parent.mkdir(parents=True, exist_ok=True)
            git("mv", src, dst)
        for src in self.removes:
            git("rm", "-q", src)
        for rel, text in self.writes.items():
            path = ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        for rel, target in self.symlinks.items():
            path = ROOT / rel
            path.unlink()
            path.symlink_to(target)
        for stale in ("cookbooks", "data", "fixtures"):
            if (ROOT / stale).exists():
                if git("ls-files", stale).strip():
                    msg = f"tracked files remain under {stale}/"
                    raise SystemExit(msg)
                shutil.rmtree(ROOT / stale)
        git("add", "-A")


# --------------------------------------------------------------------------
# README


README = """\
# zygon-knowledge

The assistant's knowledge base for pypsa-app. The app pins one commit of this
repo (`KNOWLEDGE_REV` in its `src/agent/knowledge.py`) and reads the cards
below at runtime; bump the pin to ship new content.

## Layout

| path | what | shape |
|---|---|---|
| `topics/<slug>.yaml` | one card per planning question, seven of them | `id, title, question, when_to_use[], models[]` where each `models[]` entry is `{model, coverage, gap_assessment, recipes{generation_conversion[], demand[]}, methods[{id, role}], defaults[], plots[], version_anchor{ref, date}}` |
| `recipes/generation_conversion/<slug>.yaml`, `recipes/demand/<slug>.yaml` | technology and demand recipes, shared across models | `id, title, summary, when_to_use[], models[]` where each entry is `{model, version_anchor, out_of_box, levers[], boundary[{variant, rung, note}], where[], data_dependencies[]}` |
| `methods/<slug>.yaml` or `methods/<slug>/spec.yaml` + `payload/<model>/` | executable method specs, only the ones a topic cites | `id, title, family, what, when_to_use[], models[]` with `execution[]`, `invalidates[]`, `budget`, `success_metric[]` per entry |
| `data_quality/<model>/countries/<CC>.yaml` | per-country data-quality scorecards (generated), with `datasets.yaml`, `MATRIX.csv`, `INDEX.md` | |
| `baselines/<model>/` | the settled baseline `manifest.yaml` and its `config[.<variant>].yaml` overlays | |
| `policy/` | the energy policy registry (assets, targets, subsidies, regulation as CSV) and its tools | |
| `basemaps/` | admin0/admin1/land GeoJSON for the plot cards | |
| `models/<model>` | submodules, the version anchor every card cites | |
| `archive/` | the pre-restructure content the app does not read (see below) | |

## How the app reads it

A card is written once for every model it applies to. The app opens
`topics/<slug>.yaml`, picks the `models[]` entry whose `model` matches the
network in front of the user, and reads `coverage` and `gap_assessment` before
anything else. A topic is listed for a model only when it has an entry for it.
A model's entry names only recipes and methods that exist with an entry for
that model; `archive/tools/restructure.py --validate` enforces that and is the
check to run after editing. `plots[].id` refer to pypsa-app's own plot cards.
There is no version marker: everything outside `archive/` is current.

## archive/

Never read by the app. Holds, at their old relative paths: the v1 topic cards
of both models and their capability registries (`FUNCTIONALITY.yaml`), the v1
method essays, the unverified method specs, every `_qa` checker and evidence
file, the generated data-quality maps, the old per-model READMEs and indexes,
`fixtures/BASELINE.md` and the fixture network symlinks, plus
`tools/restructure.py`, the script that produced this layout.

## Checks

```
python3 archive/tools/restructure.py --validate
```

## Anchors

Earth cards cite the `models/pypsa-earth` submodule commit. Eur cards cite
`849c8858`, a fork branch commit that is not in any public remote; the
`models/pypsa-eur` submodule pin points at upstream. See
`archive/fixtures/BASELINE.md`.
"""


# --------------------------------------------------------------------------
# main


def preflight(allow_head: bool) -> None:
    dirty = [
        ln
        for ln in git("status", "--porcelain").split("\n")
        if ln and not ln.endswith("archive/tools/restructure.py") and not ln.endswith("archive/")
    ]
    if dirty:
        msg = "working tree is not clean:\n" + "\n".join(dirty)
        raise SystemExit(msg)
    head = git("rev-parse", "HEAD").strip()
    if head != EXPECTED_HEAD and not allow_head:
        msg = f"HEAD is {head[:7]}, expected {EXPECTED_HEAD[:7]} (use --allow-head)"
        raise SystemExit(msg)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate", action="store_true", help="only check the current tree")
    ap.add_argument("--allow-head", action="store_true")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    args = ap.parse_args()

    if args.validate:
        topics, recipe_models, method_models, errors = scan_disk()
        errors += validate(topics, recipe_models, method_models)
        for e in errors:
            print("ERROR", e)
        print("ok" if not errors else f"{len(errors)} error(s)")
        return 1 if errors else 0

    preflight(args.allow_head)
    plan = Plan(Repo(), args.date)
    plan.report()
    if plan.errors:
        return 1
    if args.dry_run:
        for src, dst in plan.moves:
            print(f"mv  {src} -> {dst}")
        for src in plan.removes:
            print(f"rm  {src}")
        for rel, text in plan.writes.items():
            print(f"wr  {rel} ({len(text)} chars)")
        for rel, target in plan.symlinks.items():
            print(f"ln  {rel} -> {target}")
        return 0
    plan.apply()
    topics, recipe_models, method_models, errors = scan_disk()
    errors += validate(topics, recipe_models, method_models)
    for e in errors:
        print("ERROR", e)
    print(git("diff", "--cached", "-M", "--stat").strip().split("\n")[-1])
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
