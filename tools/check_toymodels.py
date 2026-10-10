#!/usr/bin/env python3
"""Check the toy models' figures against pypsa-app's own figure validator.

Needs the app venv (pypsa-app is not a dependency of this repo, it is the consumer):

    cd ../pypsa-app && uv run python ../zygon-knowledge/tools/check_toymodels.py [--rerun]

Every `toymodels/<slug>/figures/*.json` is parsed by
`pypsa_app.backend.services.figures.spec.validate_figure` with the app's size cap, the
same function the app runs on a figure the assistant writes. `--rerun` also executes
every `model.py` (or the slugs given) into a temporary directory and compares the
regenerated figure files byte for byte and the numbers (minus wall-clock `*_s` keys) with
the committed ones, so a model that drifts (an unseeded
random draw, a solver tie) is caught here. `--app` points at another app checkout.
"""

from __future__ import annotations

import argparse
import filecmp
import importlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOYMODELS = ROOT / "toymodels"


def load_validator(app: Path):
    src = app / "src"
    if not (src / "pypsa_app").exists():
        raise SystemExit(f"no pypsa_app package under {src}")
    sys.path.insert(0, str(src))
    spec = importlib.import_module("pypsa_app.backend.services.figures.spec")
    templates = importlib.import_module("pypsa_app.backend.services.agent.figure_templates")
    return spec.validate_figure, spec.FigureSpecError, templates.FIGURE_JSON_MAX_BYTES


def model_dirs() -> list[Path]:
    return sorted(p for p in TOYMODELS.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "model.py").exists())


def check_figures(validate, error_cls, max_bytes: int) -> list[str]:
    errors: list[str] = []
    count = 0
    for mdir in model_dirs():
        for fig in sorted((mdir / "figures").glob("*.json")):
            count += 1
            try:
                validate(fig.read_bytes(), max_bytes=max_bytes)
            except error_cls as exc:
                errors.append(f"{fig.relative_to(ROOT)}: {exc}")
    print(f"{count} figure(s) checked against the app validator")
    return errors


def _strip_timings(node):
    """Drop wall-clock keys (`*_s`) before comparing numbers: they are not deterministic."""
    if isinstance(node, dict):
        return {k: _strip_timings(v) for k, v in node.items() if not str(k).endswith("_s")}
    if isinstance(node, list):
        return [_strip_timings(v) for v in node]
    return node


def check_rerun(only: list[str] | None = None) -> list[str]:
    sys.path.insert(0, str(TOYMODELS))
    from _lib import run  # noqa: E402

    errors: list[str] = []
    for mdir in model_dirs():
        if only and mdir.name not in only:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / mdir.name
            out.mkdir()
            try:
                run.run(mdir.name, outdir=out)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{mdir.name}: rerun failed: {exc}")
                continue
            committed = sorted(p.name for p in (mdir / "figures").glob("*.json"))
            fresh = sorted(p.name for p in (out / "figures").glob("*.json"))
            if committed != fresh:
                errors.append(f"{mdir.name}: figure set differs: {committed} vs {fresh}")
                continue
            for name in committed:
                if not filecmp.cmp(mdir / "figures" / name, out / "figures" / name, shallow=False):
                    errors.append(f"{mdir.name}/figures/{name}: rerun differs from the committed file")
            # results.yaml carries the runtime, so compare the numbers block only
            import yaml

            a = _strip_timings(yaml.safe_load((mdir / "results.yaml").read_text())["numbers"])
            b = _strip_timings(yaml.safe_load((out / "results.yaml").read_text())["numbers"])
            if a != b:
                errors.append(f"{mdir.name}/results.yaml: numbers differ on rerun")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", type=Path, default=ROOT.parent / "pypsa-app", help="pypsa-app checkout")
    ap.add_argument("--rerun", action="store_true", help="re-execute every model and diff the outputs")
    ap.add_argument("slugs", nargs="*", help="limit --rerun to these models")
    args = ap.parse_args()

    validate, error_cls, max_bytes = load_validator(args.app.resolve())
    errors = check_figures(validate, error_cls, max_bytes)
    if args.rerun:
        errors += check_rerun(args.slugs)
    for e in errors:
        print("ERROR", e)
    print("ok" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
