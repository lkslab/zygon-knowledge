# SPDX-License-Identifier: MIT
"""Run toy models and write their outputs.

    cd ../pypsa-app && uv run python <zygon-knowledge>/toymodels/_lib/run.py [slug ...]

With no slug every model directory under `toymodels/` runs. Each `model.py` exposes
`build()`, `solve(n)`, `numbers(n)` and `figures(n)`; `emit()` here writes
`figures/<id>.json`, `results.yaml` and `preview.html` beside it. Output is
deterministic (seeded profiles, HiGHS), so a rerun reproduces the committed files.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pypsa

TOYMODELS = Path(__file__).resolve().parents[1]

if __package__ in (None, ""):
    # Run as a script: make `toymodels/` importable and use the package path, so the
    # `_lib.bundle` a model imports is the same module this file writes with.
    if str(TOYMODELS) not in sys.path:
        sys.path.insert(0, str(TOYMODELS))
    from _lib import bundle
else:
    from . import bundle
SOLVER = "highs"
QUIET_SOLVER = {"output_flag": False, "log_to_console": False}


def quiet() -> None:
    """Silence linopy/pypsa/highs chatter so a run prints only what a model prints."""
    for name in ("linopy", "pypsa", "highspy"):
        logging.getLogger(name).setLevel(logging.ERROR)
    # pandas 3 string dtype: keep PyPSA 1.x's object dtype explicitly (silences a FutureWarning)
    pypsa.options.api.legacy_string_dtype = False


def solve(n: pypsa.Network, **kwargs: Any) -> pypsa.Network:
    """`n.optimize()` with HiGHS, quiet; raises unless the solve ended optimal.

    `n.objective` keeps the constant term (capital cost of fixed capacities), so it is
    the total system cost of the snapshots solved.
    """
    quiet()
    opts = {**QUIET_SOLVER, **kwargs.pop("solver_options", {})}
    has_mip = bool(len(n.generators) and n.generators.committable.any())
    has_qp = bool(len(n.generators) and "marginal_cost_quadratic" in n.generators and n.generators.marginal_cost_quadratic.any())
    if not has_mip and not has_qp:
        opts.setdefault("solver", "ipm")  # faster than simplex on the year-long LPs, duals intact; HiGHS ipm rejects QPs
    kwargs.setdefault("include_objective_constant", True)
    kwargs.setdefault("progress", False)
    status, condition = n.optimize(solver_name=SOLVER, solver_options=opts, **kwargs)
    if status != "ok" or condition != "optimal":
        raise RuntimeError(f"solve ended {status}/{condition}")
    # a network with an attached solver model cannot be copied; results are already on n
    try:
        n.model.solver_model = None
    except AttributeError:
        pass
    return n


def model_dirs() -> list[Path]:
    return sorted(p for p in TOYMODELS.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "model.py").exists())


def load_model(slug: str) -> ModuleType:
    """Import `toymodels/<slug>/model.py` by path (hyphenated dirs are not packages)."""
    path = TOYMODELS / slug / "model.py"
    if not path.exists():
        raise FileNotFoundError(path)
    if str(TOYMODELS) not in sys.path:
        sys.path.insert(0, str(TOYMODELS))
    spec = importlib.util.spec_from_file_location(f"toymodel_{slug.replace('-', '_')}", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def emit(
    slug: str,
    figures: dict[str, bundle.Figure],
    numbers: dict[str, Any],
    *,
    title: str,
    subtitle: str = "",
    runtime_s: float | None = None,
    outdir: Path | None = None,
) -> Path:
    """Write figures/<id>.json, results.yaml and preview.html for one model."""
    out = outdir or (TOYMODELS / slug)
    figdir = out / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    for stale in figdir.glob("*.json"):
        if stale.stem not in figures:
            stale.unlink()
    for fig_id, fig in figures.items():
        bundle.write_figure(figdir / f"{fig_id}.json", fig)
    meta = {
        "pypsa": pypsa.__version__,
        "solver": SOLVER,
        "runtime_s": round(runtime_s, 2) if runtime_s is not None else None,
        "figures": {fid: {"title": f.title, "file": f"figures/{fid}.json", "height": f.height} for fid, f in figures.items()},
    }
    bundle.write_results(out / "results.yaml", numbers, meta)
    bundle.write_preview(out / "preview.html", title, figures, subtitle=subtitle, numbers=numbers)
    return out


def run(slug: str, outdir: Path | None = None) -> dict[str, Any]:
    mod = load_model(slug)
    t0 = time.perf_counter()
    result = mod.main(outdir=outdir, runtime_start=t0)
    return result


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    slugs = args or [p.name for p in model_dirs()]
    quiet()
    failed = 0
    for slug in slugs:
        t0 = time.perf_counter()
        try:
            run(slug)
        except Exception as exc:  # noqa: BLE001 - report and continue
            failed += 1
            print(f"FAIL {slug}: {exc}")
            continue
        print(f"ok   {slug} ({time.perf_counter() - t0:.1f}s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
