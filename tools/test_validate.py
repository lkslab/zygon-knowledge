"""validate_payloads: the pypsa-eur payload shape, one failure class per test."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from validate import validate_payloads  # noqa: E402

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
