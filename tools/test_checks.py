"""Checks: payload shape, anchors and citations, one failure class per test."""

from __future__ import annotations

from pathlib import Path

import yaml
from checks import anchor_errors, citation_errors, validate_payloads
from knowledge import MODELS, Knowledge

RULE = 'rule x:\n    script:\n        "{path}"\n'


def make(
    root: Path,
    *,
    config: str | None = "foo:\n  a: 1\n",
    rules: dict[str, str] | None = None,
    edits: bool = False,
    method: str = "m",
) -> Path:
    payload = root / "methods" / method / "payload" / "pypsa-eur"
    payload.mkdir(parents=True)
    if config is not None:
        (payload / "config.yaml").write_text(config)
    if rules is None:
        rules = {"x.smk": RULE.format(path="../scripts/x.py")}
    rules_dir = payload / "new" / "rules"
    rules_dir.mkdir(parents=True)
    for name, text in rules.items():
        (rules_dir / name).write_text(text)
    (payload / "new" / "scripts").mkdir()
    if edits:
        (payload / "edits").mkdir()
    return payload


def test_well_shaped_tree_passes(tmp_path: Path) -> None:
    make(tmp_path)
    assert validate_payloads(tmp_path) == []


def test_scripts_helper_is_exempt(tmp_path: Path) -> None:
    make(tmp_path, rules={"x.smk": "rule x:\n    script:\n        scripts('../../a.py')\n"})
    assert validate_payloads(tmp_path) == []


def test_edits_dir_reported(tmp_path: Path) -> None:
    make(tmp_path, edits=True)
    assert any("edits/" in e for e in validate_payloads(tmp_path))


def test_unparsable_fragment_reported(tmp_path: Path) -> None:
    make(tmp_path, config="foo: [unclosed\n")
    assert any("config.yaml" in e and "parse" in e for e in validate_payloads(tmp_path))


def test_non_mapping_fragment_reported(tmp_path: Path) -> None:
    make(tmp_path, config="- a\n- b\n")
    assert any("config.yaml" in e and "mapping" in e for e in validate_payloads(tmp_path))


def test_missing_fragment_reported(tmp_path: Path) -> None:
    make(tmp_path, config=None)
    assert any("config.yaml" in e and "missing" in e for e in validate_payloads(tmp_path))


def test_missing_rules_dir_reported(tmp_path: Path) -> None:
    payload = make(tmp_path)
    (payload / "new" / "rules" / "x.smk").unlink()
    (payload / "new" / "rules").rmdir()
    assert any("new/rules" in e for e in validate_payloads(tmp_path))


def test_rules_dir_without_smk_reported(tmp_path: Path) -> None:
    make(tmp_path, rules={})
    assert any("*.smk" in e for e in validate_payloads(tmp_path))


def test_escaping_script_reported(tmp_path: Path) -> None:
    make(tmp_path, rules={"x.smk": RULE.format(path="../../escape.py")})
    errors = validate_payloads(tmp_path)
    assert any("escape.py" in e and "outside" in e for e in errors)


def test_pypsa_earth_not_scanned(tmp_path: Path) -> None:
    earth = tmp_path / "methods" / "m" / "payload" / "pypsa-earth"
    earth.mkdir(parents=True)
    (earth / "edits").mkdir()
    assert validate_payloads(tmp_path) == []


CANONICAL = "a" * 40
OTHER = "b" * 40


def put(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc))


def anchor(ref: str) -> dict:
    return {"ref": ref, "date": "2026-10-12"}


def tree(
    root: Path,
    *,
    topic_anchor: str | None = CANONICAL,
    carrier_ref: str = CANONICAL,
    cited: tuple[str, ...] = ("m",),
    methods: tuple[str, ...] = ("m",),
    method_models: tuple[str, ...] = MODELS,
) -> Path:
    """A minimal tree for both models: topic `t`, carrier `c`, method files."""
    section = {"approach": "a", "trade_offs": [], "limitations": []}
    topic_models = []
    for model in MODELS:
        entry = {**section, "model": model, "methods": [{"id": m} for m in cited]}
        if topic_anchor is not None:
            entry["version_anchor"] = anchor(topic_anchor)
        topic_models.append(entry)
    put(
        root / "topics" / "t.yaml",
        {"id": "t", "title": "T", "question": "q", "when_to_use": [], "models": topic_models},
    )
    put(
        root / "carriers" / "demand" / "c.yaml",
        {
            "id": "c",
            "title": "C",
            "summary": "s",
            "when_to_use": [],
            "models": [
                {
                    "model": model,
                    "version_anchor": anchor(carrier_ref),
                    "out_of_box": {},
                    "levers": [],
                    "boundary": [],
                }
                for model in MODELS
            ],
        },
    )
    for method in methods:
        put(
            root / "methods" / f"{method}.yaml",
            {
                "id": method,
                "title": "M",
                "what": "w",
                "when_to_use": [],
                "models": [
                    {"model": model, "version_anchor": anchor(CANONICAL)}
                    for model in method_models
                ],
            },
        )
    return root


def handle(root: Path, model: str = "pypsa-eur") -> Knowledge:
    opened = Knowledge.open(root, model)
    assert opened is not None
    return opened


def test_well_formed_tree_passes(tmp_path: Path) -> None:
    h = handle(tree(tmp_path))
    assert anchor_errors(h, CANONICAL) == []
    assert citation_errors(h) == []


def test_other_carrier_ref_reported(tmp_path: Path) -> None:
    errors = anchor_errors(handle(tree(tmp_path, carrier_ref=OTHER)), CANONICAL)
    assert len(errors) == 1
    assert "carriers/demand/c" in errors[0]
    assert "not the canonical" in errors[0]


def test_topic_without_anchor_reported(tmp_path: Path) -> None:
    errors = anchor_errors(handle(tree(tmp_path, topic_anchor=None)), CANONICAL)
    assert errors == ["topics/t/pypsa-eur: no version_anchor"]


def test_cited_method_without_file_reported(tmp_path: Path) -> None:
    errors = citation_errors(handle(tree(tmp_path, cited=("m", "ghost"))))
    assert len(errors) == 1
    assert errors[0].startswith("topics/t/pypsa-eur: method ghost")


def test_uncited_method_reported(tmp_path: Path) -> None:
    errors = citation_errors(handle(tree(tmp_path, methods=("m", "extra"))))
    assert errors == ["methods/extra/pypsa-eur: not cited by any topic"]


def test_cited_method_without_model_section_reported(tmp_path: Path) -> None:
    root = tree(tmp_path, method_models=("pypsa-earth",))
    errors = citation_errors(handle(root))
    assert len(errors) == 1
    assert "methods/m has no pypsa-eur section" in errors[0]
