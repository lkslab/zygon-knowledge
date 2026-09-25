# SPDX-License-Identifier: MIT
"""Writers for a toy model's outputs: figure.json bundles, results.yaml, preview.html.

A figure bundle is pypsa-app's artifact contract (`figure_spec.py` there):
`{"version": 1, "option": <ECharts option>, "datasets": {id: {columns, rows}},
"height": px}`. The option holds no rows and no title; series bind to a dataset by
`datasetId`. `check_figure` mirrors the app validator's structural rules so a model
fails here, at build time, rather than in the app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import carrier_style as cs

MIN_HEIGHT, DEFAULT_HEIGHT, MAX_HEIGHT = 240, 360, 960
MAX_SERIES = 50
MAX_OPTION_BYTES = 256 * 1024
MAX_TOTAL_CELLS = 200_000
SERIES_TYPES = {"bar", "line", "scatter", "heatmap", "pie", "sankey", "boxplot", "graph", "map", "lines"}
BLOCKED_KEYS = {"toolbox", "graphic"}


@dataclass
class Figure:
    """One chart: its option, the datasets it reads, and the prose the card shows around it."""

    option: dict[str, Any]
    datasets: dict[str, dict[str, Any]]
    title: str
    caption: str = ""
    height: int | None = None
    unit: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # `charts.bars` computes a height for horizontal bars and passes it this way.
        carried = self.option.pop("_height", None)
        if self.height is None:
            self.height = int(carried) if carried else DEFAULT_HEIGHT
        self.height = max(MIN_HEIGHT, min(MAX_HEIGHT, self.height))

    def bundle(self) -> dict[str, Any]:
        return {"version": 1, "option": self.option, "datasets": self.datasets, "height": self.height}


def check_figure(fig: Figure) -> list[str]:
    """Structural findings, in the spirit of the app's `validate_figure` (subset)."""
    errors: list[str] = []
    option = fig.option
    if "title" in option:
        errors.append("option.title is set; the app frame owns the title")
    for key in BLOCKED_KEYS:
        if key in option:
            errors.append(f"option.{key} is not allowed")
    entries = option.get("dataset") or []
    if isinstance(entries, dict):
        entries = [entries]
    declared = set()
    for entry in entries:
        if "id" not in entry:
            errors.append("dataset entry without id")
            continue
        declared.add(entry["id"])
        if "source" in entry:
            errors.append(f"dataset {entry['id']!r} carries an inline source")
        if entry["id"] not in fig.datasets:
            errors.append(f"dataset {entry['id']!r} missing from datasets")
    for ds_id in fig.datasets:
        if ds_id not in declared:
            errors.append(f"datasets.{ds_id} is never declared in option.dataset")
    series = option.get("series") or []
    if len(series) > MAX_SERIES:
        errors.append(f"{len(series)} series, cap is {MAX_SERIES}")
    for i, s in enumerate(series):
        if s.get("type") not in SERIES_TYPES:
            errors.append(f"series[{i}] type {s.get('type')!r} not in the allowed set")
        ds_id = s.get("datasetId")
        if ds_id is not None and ds_id not in declared:
            errors.append(f"series[{i}] datasetId {ds_id!r} does not resolve")
        if ds_id is None and s.get("type") != "sankey" and "data" not in s:
            errors.append(f"series[{i}] has neither datasetId nor data")

    def walk(node: Any, path: str) -> None:
        if callable(node):
            errors.append(f"{path} is a function")
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for j, v in enumerate(node):
                walk(v, f"{path}[{j}]")

    walk(option, "option")
    cells = sum(len(d["columns"]) * len(d["rows"]) for d in fig.datasets.values())
    if cells > MAX_TOTAL_CELLS:
        errors.append(f"{cells} dataset cells, cap is {MAX_TOTAL_CELLS}")
    option_bytes = len(json.dumps(option).encode())
    if option_bytes > MAX_OPTION_BYTES:
        errors.append(f"option is {option_bytes} bytes, cap is {MAX_OPTION_BYTES}")
    if not (MIN_HEIGHT <= (fig.height or 0) <= MAX_HEIGHT):
        errors.append(f"height {fig.height} outside {MIN_HEIGHT}..{MAX_HEIGHT}")
    return errors


def write_figure(path: Path, fig: Figure) -> Path:
    errors = check_figure(fig)
    if errors:
        raise ValueError(f"{path.name}: " + "; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fig.bundle(), separators=(",", ":"), ensure_ascii=False) + "\n")
    return path


def clean(v: Any) -> Any:
    """Plain JSON/YAML values: numpy scalars unwrapped, floats rounded to 4 decimals."""
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return int(v)
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float):
        return round(v, 4)
    return v


def write_results(path: Path, numbers: dict[str, Any], meta: dict[str, Any]) -> Path:
    """`results.yaml`: the headline numbers (rounded) under `numbers`, run info under `meta`."""
    doc = {"numbers": clean(numbers), "meta": clean(meta)}
    path.write_text(yaml.safe_dump(doc, sort_keys=False, width=100, allow_unicode=True))
    return path


# ── preview.html ─────────────────────────────────────────────────────────────

_PREVIEW_CSS = """
:root { --bg:#ffffff; --fg:#171717; --muted:#6b7280; --border:#e5e5e5; --card:#ffffff; }
html.dark { --bg:#191919; --fg:#e5e5e5; --muted:#9ca3af; --border:#333333; --card:#222222; }
body { margin:0; background:var(--bg); color:var(--fg);
  font-family: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; font-size:12px; }
main { max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 18px; font-weight: 600; margin: 0 0 4px; }
.sub { color: var(--muted); font-size: 12.5px; margin: 0 0 20px; }
.card { border: 1px solid var(--border); border-radius: 24px; padding: 16px 20px; margin: 12px 0;
  background: var(--card); }
.title { font-size: 14px; font-weight: 600; }
.caption { color: var(--muted); font-size: 12.5px; margin-top: 6px; }
.chart { width: 720px; max-width: 100%; margin: 4px 0; }
.bar { display:flex; justify-content: space-between; align-items: baseline; }
button { font: inherit; background: none; color: var(--fg); border: 1px solid var(--border);
  border-radius: 8px; padding: 4px 10px; cursor: pointer; }
table.numbers { border-collapse: collapse; margin: 8px 0 16px; font-size: 12.5px; }
table.numbers td { padding: 2px 12px 2px 0; border-bottom: 1px solid var(--border); }
table.numbers td:nth-child(2) { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; text-align: right; }
"""

_PREVIEW_JS = """
const FIGURES = __FIGURES__;
const CARRIER_COLOURS = __COLOURS__;
const NUMBERS = __NUMBERS__;
const charts = [];
function bound(fig) {
  const option = JSON.parse(JSON.stringify(fig.option));
  const entries = Array.isArray(option.dataset) ? option.dataset : (option.dataset ? [option.dataset] : []);
  for (const entry of entries) {
    const ds = fig.datasets[entry.id];
    if (ds && !entry.source) entry.source = [ds.columns, ...ds.rows];
  }
  for (const s of option.series || []) {
    const colour = CARRIER_COLOURS[s.name];
    if (colour && !(s.itemStyle && s.itemStyle.color)) {
      s.itemStyle = Object.assign({}, s.itemStyle, {color: colour});
      if (s.type === "line") s.lineStyle = Object.assign({}, s.lineStyle, {color: colour});
    }
  }
  // The app measures the bottom legend and pushes the grid up by its height; approximate that.
  const legend = option.legend;
  if (legend && legend.bottom === 0 && Array.isArray(legend.data)) {
    const chars = legend.data.reduce((a, n) => a + String(n).length * 7.5 + 12 + 14, 0);
    const rows = Math.max(1, Math.ceil(chars / 700));
    const room = rows * 20 + 10;
    const grids = Array.isArray(option.grid) ? option.grid : [option.grid || {}];
    for (const g of grids) g.bottom = (typeof g.bottom === "number" ? g.bottom : 8) + room;
    option.grid = Array.isArray(option.grid) ? grids : grids[0];
    for (const z of option.dataZoom || []) if (typeof z.bottom === "number") z.bottom += room;
  }
  return Object.assign({backgroundColor: "transparent", textStyle: {fontFamily: "inherit"}}, option);
}
function render() {
  const dark = document.documentElement.classList.contains("dark");
  for (const c of charts) c.dispose();
  charts.length = 0;
  for (const [id, fig] of Object.entries(FIGURES)) {
    const el = document.getElementById("chart-" + id);
    el.style.height = (fig.height || 360) + "px";
    const chart = echarts.init(el, dark ? "dark" : undefined);
    chart.setOption(bound(fig), true);
    charts.push(chart);
  }
}
document.getElementById("theme").addEventListener("click", () => {
  document.documentElement.classList.toggle("dark");
  render();
});
window.addEventListener("resize", () => charts.forEach(c => c.resize()));
render();
"""


def write_preview(
    path: Path,
    title: str,
    figures: dict[str, Figure],
    *,
    subtitle: str = "",
    numbers: dict[str, Any] | None = None,
) -> Path:
    """One standalone page per model, ECharts 6 from a CDN, light/dark toggle.

    The page does what pypsa-app's `bindFigure` does: fills each `option.dataset`
    entry from the datasets map (header row plus rows), colours carrier-named series
    from the style snapshot, and puts title and caption in the DOM around a 720 px
    canvas the way the app's chart frame does.
    """
    cards = []
    for fig_id, fig in figures.items():
        cards.append(
            f'<section class="card"><div class="title">{fig.title}</div>'
            f'<div id="chart-{fig_id}" class="chart"></div>'
            f'<div class="caption">{fig.caption}</div></section>'
        )
    numbers_html = ""
    if numbers:
        rows = []
        for k, v in clean(numbers).items():
            if isinstance(v, dict):
                rows += [f"<tr><td>{k} / {kk}</td><td>{vv}</td></tr>" for kk, vv in v.items()]
            else:
                rows.append(f"<tr><td>{k}</td><td>{v}</td></tr>")
        numbers_html = f'<table class="numbers">{"".join(rows)}</table>'
    payload = {fid: fig.bundle() for fid, fig in figures.items()}
    colours = {k: v[1] for k, v in cs.CARRIERS.items()}
    js = (
        _PREVIEW_JS.replace("__FIGURES__", json.dumps(payload))
        .replace("__COLOURS__", json.dumps(colours))
        .replace("__NUMBERS__", json.dumps(numbers or {}, default=str))
    )
    html = (
        "<!doctype html>\n<html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<style>{_PREVIEW_CSS}</style>"
        "<script src='https://cdn.jsdelivr.net/npm/echarts@6/dist/echarts.min.js'></script>"
        "</head><body><main>"
        f'<div class="bar"><h1>{title}</h1><button id="theme">light / dark</button></div>'
        f'<p class="sub">{subtitle}</p>'
        f"{numbers_html}"
        f"{''.join(cards)}"
        f"</main><script>{js}</script></body></html>\n"
    )
    path.write_text(html)
    return path
