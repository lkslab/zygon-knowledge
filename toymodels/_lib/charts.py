# SPDX-License-Identifier: MIT
"""House-style ECharts option builders, mirroring pypsa-app's `figure_templates.py`.

Every builder returns `(option, datasets)`: a plain-JSON ECharts option whose series
read their rows from `datasets` through `datasetId` + `encode`, never inline. The
option carries no `title` (the app's card frame owns it), the legend sits below the
chart, the value axis is named with its unit, category labels wrap and never rotate.

Colour policy: a series named after a carrier id (see `carrier_style.CARRIERS`) gets
no colour, the client colours it; any other series gets the next Okabe-Ito colour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from . import carrier_style as cs

# ── house constants (values copied from pypsa-app figure_templates.py) ──────

LEGEND_STYLE: dict[str, Any] = {"icon": "roundRect", "itemWidth": 12, "itemHeight": 12, "itemGap": 14}
LEGEND: dict[str, Any] = {**LEGEND_STYLE, "bottom": 0, "left": 0, "type": "plain"}
GRID: dict[str, Any] = {"left": 8, "right": 24, "top": 24, "bottom": 8, "containLabel": True}
AXIS_NAME_MARGIN = 44
AXIS_LABEL: dict[str, Any] = {"hideOverlap": True}
BAR_TOOLTIP: dict[str, Any] = {"trigger": "axis", "axisPointer": {"type": "shadow"}}
LINE_TOOLTIP: dict[str, Any] = {"trigger": "axis", "axisPointer": {"type": "cross", "animation": False}}
BAR_MAX_WIDTH = 40
CURVE_POINTS = 400
WITHDRAWAL_SUFFIX = " (withdrawal)"
HORIZONTAL_ABOVE = 6
LONG_LABEL = 18
DECIMALS = 3
# fill_between bands: what flows to the asset below the level, what flows back above it
BAND_BELOW = "#009e73"  # Okabe-Ito bluish green
BAND_ABOVE = "#d55e00"  # Okabe-Ito vermillion
PANEL_GAP = 40

Option = dict[str, Any]
Datasets = dict[str, dict[str, Any]]


# ── datasets ────────────────────────────────────────────────────────────────


def _cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(value, (np.floating, float)):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(float(value), DECIMALS)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def dataset(columns: list[str], rows: list[list[Any]]) -> dict[str, Any]:
    return {"columns": list(columns), "rows": [[_cell(v) for v in row] for row in rows]}


def dataset_from_frame(df: pd.DataFrame, index_name: str = "x") -> dict[str, Any]:
    """Columns = [index_name, *df.columns]; a DatetimeIndex is written as ISO strings."""
    columns = [index_name, *(str(c) for c in df.columns)]
    rows = [[idx, *vals] for idx, vals in zip(df.index, df.to_numpy().tolist())]
    return dataset(columns, rows)


# ── axes ────────────────────────────────────────────────────────────────────


def value_axis(unit: str, **extra: Any) -> dict[str, Any]:
    """A vertical value axis with the unit rotated along its middle."""
    return {
        "type": "value",
        "name": unit,
        "nameLocation": "middle",
        "nameGap": 40,
        "splitLine": {"lineStyle": {"opacity": 0.4}},
        **extra,
    }


def time_axis() -> dict[str, Any]:
    return {
        "type": "time",
        "boundaryGap": False,
        "axisLabel": {
            **AXIS_LABEL,
            "showMinLabel": False,
            "showMaxLabel": False,
            "formatter": {
                "year": "{yyyy}",
                "month": "{MMM}",
                "day": "{d} {MMM}",
                "hour": "{HH}:{mm}",
                "minute": "{HH}:{mm}",
            },
        },
    }


def x_value_axis(name: str, **extra: Any) -> dict[str, Any]:
    """A horizontal value axis (a duration share, a capacity, a cost) named at its middle."""
    return {
        "type": "value",
        "name": name,
        "nameLocation": "middle",
        "nameGap": 26,
        "axisLine": {"onZero": False},
        "splitLine": {"show": False},
        **extra,
    }


def category_axis(categories: list[str], *, horizontal: bool = False) -> dict[str, Any]:
    axis: dict[str, Any] = {"type": "category", "data": list(categories), "axisTick": {"alignWithLabel": True}}
    if horizontal:
        axis["inverse"] = True
        axis["axisLabel"] = {**AXIS_LABEL}
    else:
        slot = max(56, min(150, 640 // max(1, len(categories)) - 10))
        axis["axisLabel"] = {"interval": 0, "width": slot, "overflow": "break", "lineHeight": 14}
    return axis


# ── series ──────────────────────────────────────────────────────────────────


class Palette:
    """Hands out Okabe-Ito colours to non-carrier series in order of appearance."""

    def __init__(self) -> None:
        self.i = 0
        self.seen: dict[str, str] = {}

    def style(self, name: str, *, line: bool) -> dict[str, Any]:
        if cs.is_carrier(name):
            return {}
        if name in self.seen:
            colour = self.seen[name]
        else:
            colour = cs.SCENARIO_PALETTE[self.i % len(cs.SCENARIO_PALETTE)]
            self.i += 1
            self.seen[name] = colour
        style: dict[str, Any] = {"itemStyle": {"color": colour}}
        if line:
            style["lineStyle"] = {"color": colour, "width": 2}
        return style


def line_series(
    name: str,
    dataset_id: str,
    x: str,
    palette: Palette,
    *,
    y: str | None = None,
    stack: str | None = None,
    area: bool = False,
    step: str | None = None,
    y_axis_index: int = 0,
    dashed: bool = False,
) -> dict[str, Any]:
    s: dict[str, Any] = {
        "type": "line",
        "name": name,
        "showSymbol": False,
        "emphasis": {"focus": "series"},
        "datasetId": dataset_id,
        "encode": {"x": x, "y": y or name},
        **palette.style(name, line=True),
    }
    if stack:
        s["stack"] = stack
    if area:
        s["areaStyle"] = {"opacity": 0.85}
        s["lineStyle"] = {**s.get("lineStyle", {}), "width": 0.5}
    if step:
        s["step"] = step
    if y_axis_index:
        s["yAxisIndex"] = y_axis_index
    if dashed:
        s["lineStyle"] = {**s.get("lineStyle", {}), "type": "dashed"}
    return s


def bar_series(
    name: str,
    dataset_id: str,
    x: str,
    palette: Palette,
    *,
    y: str | None = None,
    stack: str | None = None,
    horizontal: bool = False,
) -> dict[str, Any]:
    s: dict[str, Any] = {
        "type": "bar",
        "name": name,
        "barMaxWidth": BAR_MAX_WIDTH,
        "emphasis": {"focus": "series"},
        "datasetId": dataset_id,
        "encode": {"y": x, "x": y or name} if horizontal else {"x": x, "y": y or name},
        **palette.style(name, line=False),
    }
    if stack:
        s["stack"] = stack
    return s


def zero_line() -> dict[str, Any]:
    return {
        "silent": True,
        "symbol": "none",
        "lineStyle": {"type": "dotted", "color": cs.NEUTRAL, "width": 1},
        "label": {"show": False},
        "data": [{"yAxis": 0}],
    }


def mark_lines(marks: list[dict[str, Any]], *, axis: str = "xAxis") -> dict[str, Any]:
    """Labelled reference lines: `[{"value": 4000, "label": "breakeven"}]`."""
    return {
        "silent": True,
        "symbol": "none",
        "lineStyle": {"type": "dashed", "color": cs.NEUTRAL, "width": 1},
        "label": {"position": "insideEndTop", "fontSize": 11, "color": cs.NEUTRAL, "formatter": "{b}"},
        "data": [{axis: m["value"], "name": m.get("label", "")} for m in marks],
    }


def _legend(names: list[str]) -> dict[str, Any]:
    return {**LEGEND, "data": list(names)}


def _grid(*, named_y: bool = True, bottom: int | None = None, right: int | None = None) -> dict[str, Any]:
    grid = {**GRID}
    if named_y:
        grid["left"] = AXIS_NAME_MARGIN
    if bottom is not None:
        grid["bottom"] = bottom
    if right is not None:
        grid["right"] = right
    return grid


# ── builders ────────────────────────────────────────────────────────────────


def time_series(
    df: pd.DataFrame,
    unit: str,
    *,
    stack: bool = False,
    area: bool = False,
    step: str | None = None,
    negative_stack: list[str] | None = None,
    slider: bool | None = None,
) -> tuple[Option, Datasets]:
    """Lines (or stacked areas) over a DatetimeIndex, one series per column.

    `negative_stack` names columns stacked below zero (withdrawals in an energy balance).
    A slider dataZoom is added past 1000 snapshots unless `slider` says otherwise.
    """
    ds = dataset_from_frame(df, "snapshot")
    palette = Palette()
    series = []
    names: list[str] = []
    for col in df.columns:
        column = str(col)
        stack_name = None
        if stack:
            stack_name = "withdrawal" if negative_stack and column in negative_stack else "supply"
        # a withdrawal column named "<carrier> (withdrawal)" is shown under the carrier's
        # own name, so both halves share one legend entry and one colour (the client
        # colours by carrier id); the encode still reads the suffixed column
        name = column.removesuffix(WITHDRAWAL_SUFFIX)
        series.append(line_series(name, "ts", "snapshot", palette, y=column, stack=stack_name, area=area, step=step))
        if name not in names:
            names.append(name)
    if (df.to_numpy() < 0).any():
        series[0]["markLine"] = zero_line()
    use_slider = slider if slider is not None else len(df) > 1000
    option: Option = {
        "dataset": [{"id": "ts"}],
        "tooltip": LINE_TOOLTIP,
        "grid": _grid(bottom=80 if use_slider else None),
        "xAxis": time_axis(),
        "yAxis": value_axis(unit),
        "series": series,
    }
    if len(names) > 1:
        option["legend"] = _legend(names)
    if use_slider:
        option["dataZoom"] = [{"type": "slider", "bottom": 30, "height": 20}]
    return option, {"ts": ds}


def dual_axis(
    df: pd.DataFrame,
    left: list[str],
    right: list[str],
    left_unit: str,
    right_unit: str,
    *,
    left_area: bool = False,
    step: str | None = None,
) -> tuple[Option, Datasets]:
    """Two value axes over one time axis: `left` columns on the left, `right` on the right."""
    ds = dataset_from_frame(df, "snapshot")
    palette = Palette()
    series = [line_series(c, "ts", "snapshot", palette, area=left_area, step=step) for c in left]
    series += [line_series(c, "ts", "snapshot", palette, y_axis_index=1) for c in right]
    if (df[left].to_numpy() < 0).any():
        series[0]["markLine"] = zero_line()
    option: Option = {
        "dataset": [{"id": "ts"}],
        "tooltip": LINE_TOOLTIP,
        "grid": _grid(right=56),
        "xAxis": time_axis(),
        "yAxis": [value_axis(left_unit), value_axis(right_unit, splitLine={"show": False})],
        "series": series,
        "legend": _legend(left + right),
    }
    return option, {"ts": ds}


def xy_lines(
    df: pd.DataFrame,
    x_name: str,
    unit: str,
    *,
    step: str | None = None,
    marks: list[dict[str, Any]] | None = None,
    x_extra: dict[str, Any] | None = None,
    symbols: bool = False,
) -> tuple[Option, Datasets]:
    """Lines over a numeric x (the index of `df`), one series per column."""
    ds = dataset_from_frame(df, "x")
    palette = Palette()
    series = [line_series(str(c), "xy", "x", palette, step=step) for c in df.columns]
    if symbols:
        for s in series:
            s["showSymbol"] = True
            s["symbolSize"] = 7
    if marks:
        series[0]["markLine"] = mark_lines(marks)
    option: Option = {
        "dataset": [{"id": "xy"}],
        "tooltip": LINE_TOOLTIP,
        "grid": _grid(bottom=24),
        "xAxis": x_value_axis(x_name, **(x_extra or {})),
        "yAxis": value_axis(unit),
        "series": series,
    }
    if len(df.columns) > 1:
        option["legend"] = _legend([str(c) for c in df.columns])
    return option, {"xy": ds}


def step_curve(
    segments: pd.DataFrame,
    x_name: str,
    unit: str,
    *,
    marks: list[dict[str, Any]] | None = None,
) -> tuple[Option, Datasets]:
    """A merit-order style staircase: `segments` has columns x0, x1, y, name; one
    series per name so every step carries its carrier's colour."""
    names = list(dict.fromkeys(segments["name"]))
    columns = ["x", *names]
    rows: list[list[Any]] = []
    for _, seg in segments.iterrows():
        blank: list[Any] = [None] * len(names)
        j = names.index(seg["name"])
        r0 = [seg["x0"], *blank]
        r1 = [seg["x1"], *blank]
        r0[j + 1] = seg["y"]
        r1[j + 1] = seg["y"]
        rows += [r0, r1]
    palette = Palette()
    series = []
    for name in names:
        s = line_series(name, "steps", "x", palette)
        s["lineStyle"] = {**s.get("lineStyle", {}), "width": 3}
        s["areaStyle"] = {"opacity": 0.25}
        s["connectNulls"] = False
        series.append(s)
    if marks:
        series[0]["markLine"] = mark_lines(marks)
    option: Option = {
        "dataset": [{"id": "steps"}],
        "tooltip": {"trigger": "item"},
        "grid": _grid(bottom=24),
        "xAxis": x_value_axis(x_name, max=float(segments["x1"].max())),
        "yAxis": value_axis(unit),
        "series": series,
        "legend": _legend(names),
    }
    return option, {"steps": dataset(columns, rows)}


def bars(
    categories: list[str],
    data: dict[str, list[float]],
    unit: str,
    *,
    stack: bool = False,
    horizontal: bool | None = None,
    category_name: str = "category",
) -> tuple[Option, Datasets]:
    """Grouped or stacked bars: `data` maps series name to one value per category.

    Bars go horizontal past six categories or with a label longer than 18 characters.
    """
    names = list(data)
    horiz = horizontal
    if horiz is None:
        horiz = len(categories) > HORIZONTAL_ABOVE or max(len(c) for c in categories) > LONG_LABEL
    columns = [category_name, *names]
    rows = [[cat, *(data[nm][i] for nm in names)] for i, cat in enumerate(categories)]
    palette = Palette()
    series = [
        bar_series(nm, "bars", category_name, palette, stack="total" if stack else None, horizontal=horiz)
        for nm in names
    ]
    has_negative = any(v is not None and v < 0 for nm in names for v in data[nm])
    if has_negative and not horiz:
        series[0]["markLine"] = zero_line()
    cat_axis = category_axis(categories, horizontal=horiz)
    val_axis = value_axis(unit, axisLine={"onZero": True})
    if horiz:
        val_axis["nameGap"] = 26
        height = min(960, max(240, 80 + len(categories) * (10 + 9 * (1 if stack else len(names)))))
        option: Option = {
            "dataset": [{"id": "bars"}],
            "tooltip": BAR_TOOLTIP,
            "grid": _grid(named_y=False, bottom=24),
            "xAxis": val_axis,
            "yAxis": cat_axis,
            "series": series,
        }
    else:
        val_axis["nameGap"] = 38
        height = 360
        option = {
            "dataset": [{"id": "bars"}],
            "tooltip": BAR_TOOLTIP,
            "grid": _grid(),
            "xAxis": cat_axis,
            "yAxis": val_axis,
            "series": series,
        }
    if len(names) > 1:
        option["legend"] = _legend(names)
    option["_height"] = height
    return option, {"bars": dataset(columns, rows)}


def _resample_sorted(values: list[float], points: int) -> list[float]:
    ordered = sorted(values, reverse=True)
    if len(ordered) <= points:
        return ordered
    positions = np.linspace(0, len(ordered) - 1, points)
    return [float(ordered[int(round(p))]) for p in positions]


def duration_curves(curves: dict[str, pd.Series], unit: str, *, points: int = CURVE_POINTS) -> tuple[Option, Datasets]:
    """Sorted curves over the share of hours (0-100 %), one line per entry."""
    sampled = {name: _resample_sorted([float(v) for v in s.dropna()], points) for name, s in curves.items()}
    names = list(sampled)
    columns = ["share", *names]
    cells: dict[float, list[Any]] = {}
    for j, name in enumerate(names):
        vals = sampled[name]
        n = len(vals)
        for i, v in enumerate(vals):
            share = round(100 * i / max(1, n - 1), 3)
            cells.setdefault(share, [None] * len(names))[j] = v
    rows = [[share, *cells[share]] for share in sorted(cells)]
    palette = Palette()
    series = [{**line_series(name, "curves", "share", palette), "connectNulls": True} for name in names]
    if any(v < 0 for vals in sampled.values() for v in vals):
        series[0]["markLine"] = zero_line()
    option: Option = {
        "dataset": [{"id": "curves"}],
        "tooltip": LINE_TOOLTIP,
        "grid": _grid(bottom=24),
        "xAxis": x_value_axis("Share of hours (%)", min=0, max=100),
        "yAxis": value_axis(unit),
        "series": series,
    }
    if len(names) > 1:
        option["legend"] = _legend(names)
    return option, {"curves": dataset(columns, rows)}


@dataclass
class Band:
    """One panel of `fill_between`: a column of `df` against a constant level.

    `below` and `above` name the two filled bands (the gap under the level where the
    value falls short of it, the excess over it); the tooltip shows each band's depth,
    not its edge. The colours default to green below and vermillion above (money to
    the asset, money back); swap them when the level means the opposite. A band named
    None is not drawn, for a value that only ever falls on one side of the level.

    `under` fills the value's part up to the level from zero instead (what a limit lets
    through, say, with `above` the rest); the dashed level line then takes its colour
    and its legend entry, so the level reads as the top of that fill.
    """

    value: str
    level: float
    level_name: str
    below: str | None
    above: str | None
    unit: str
    value_name: str | None = None
    below_color: str = BAND_BELOW
    above_color: str = BAND_ABOVE
    under: str | None = None
    under_color: str = BAND_BELOW


def _band_series(band: Band, j: int, palette: Palette, step: str | None) -> list[dict[str, Any]]:
    idx = {"xAxisIndex": j, "yAxisIndex": j} if j else {}
    name = band.value_name or band.value
    value = {**line_series(name, "ts", "snapshot", palette, y=band.value, step=step), **idx}
    level_colour = band.under_color if band.under else cs.NEUTRAL
    level_name = band.under or band.level_name
    level = {**line_series(level_name, "ts", "snapshot", palette, y=f"{band.value}.level", step=step, dashed=True), **idx}
    level["lineStyle"] = {**level.get("lineStyle", {}), "color": level_colour, "width": 1.5}
    level["itemStyle"] = {"color": level_colour}
    fills = []
    if band.under:
        fills.append({
            "type": "line",
            "name": band.under,
            "showSymbol": False,
            "silent": True,
            "datasetId": "ts",
            "encode": {"x": "snapshot", "y": f"{band.value}.under", "tooltip": f"{band.value}.under"},
            "lineStyle": {"width": 0, "opacity": 0},
            "itemStyle": {"color": band.under_color},
            "areaStyle": {"color": band.under_color, "opacity": 0.3, "origin": 0},
            **({"step": step} if step else {}),
            **idx,
        })
    for side, colour in (("below", band.below_color), ("above", band.above_color)):
        if getattr(band, side) is None:
            continue
        fills.append({
            "type": "line",
            "name": getattr(band, side),
            "showSymbol": False,
            "silent": True,
            "datasetId": "ts",
            # the line runs along the band's outer edge; the area closes onto the level
            "encode": {"x": "snapshot", "y": f"{band.value}.{side}.edge", "tooltip": f"{band.value}.{side}"},
            "lineStyle": {"width": 0, "opacity": 0},
            "itemStyle": {"color": colour},
            "areaStyle": {"color": colour, "opacity": 0.35, "origin": band.level},
            **({"step": step} if step else {}),
            **idx,
        })
    return [*fills, value, level]


def fill_between(df: pd.DataFrame, bands: Band | list[Band], *, step: str | None = "middle") -> tuple[Option, Datasets]:
    """A value against a constant level over a DatetimeIndex, the gap between them filled:
    one colour where the value is below the level, another where it is above.

    A list of bands stacks one panel per band on a shared time axis (the top panels'
    time labels hidden), each with its own value axis; one legend below them all.
    """
    bands = [bands] if isinstance(bands, Band) else list(bands)
    frame = pd.DataFrame(index=df.index)
    for band in bands:
        v = df[band.value].astype(float)
        frame[band.value] = v
        frame[f"{band.value}.level"] = band.level
        frame[f"{band.value}.below.edge"] = v.clip(upper=band.level)
        frame[f"{band.value}.above.edge"] = v.clip(lower=band.level)
        frame[f"{band.value}.below"] = (band.level - v).clip(lower=0)
        frame[f"{band.value}.above"] = (v - band.level).clip(lower=0)
        if band.under:
            frame[f"{band.value}.under"] = v.clip(upper=band.level)
    palette = Palette()
    series: list[dict[str, Any]] = []
    names: list[str] = []
    for j, band in enumerate(bands):
        series += _band_series(band, j, palette, step)
        for name in (band.value_name or band.value, band.under or band.level_name, band.below, band.above):
            if name is not None and name not in names:
                names.append(name)
    panel_h = 200
    if len(bands) == 1:
        grid: Any = _grid(bottom=24)
        x_axis: Any = time_axis()
        y_axis: Any = value_axis(bands[0].unit)
        height = 360
    else:
        grid, x_axis, y_axis = [], [], []
        for j, band in enumerate(bands):
            last = j == len(bands) - 1
            g = {**GRID, "left": AXIS_NAME_MARGIN, "top": GRID["top"] + j * (panel_h + PANEL_GAP)}
            if last:
                g["bottom"] = 24
            else:
                g.pop("bottom")
                g["height"] = panel_h
            grid.append(g)
            ax = {**time_axis(), "gridIndex": j}
            if not last:
                ax["axisLabel"] = {**ax["axisLabel"], "show": False}
            x_axis.append(ax)
            y_axis.append({**value_axis(band.unit), "gridIndex": j})
        height = GRID["top"] + len(bands) * panel_h + (len(bands) - 1) * PANEL_GAP + 56
    option: Option = {
        "dataset": [{"id": "ts"}],
        "tooltip": LINE_TOOLTIP,
        "grid": grid,
        "xAxis": x_axis,
        "yAxis": y_axis,
        "series": series,
        "legend": _legend(names),
        "_height": height,
    }
    if len(bands) > 1:
        option["axisPointer"] = {"link": [{"xAxisIndex": "all"}]}
    return option, {"ts": dataset_from_frame(frame, "snapshot")}


def status_steps(df: pd.DataFrame) -> tuple[Option, Datasets]:
    """0/1 commitment status per unit as offset step lines (unit i drawn at i + status*0.8)."""
    offset = pd.DataFrame({c: df[c].astype(float) * 0.8 + i for i, c in enumerate(df.columns)}, index=df.index)
    option, ds = time_series(offset, "", step="end", slider=False)
    option["yAxis"] = {
        "type": "value",
        "min": 0,
        "max": len(df.columns),
        "interval": 1,
        "axisLabel": {"show": False},
        "splitLine": {"lineStyle": {"opacity": 0.4}},
    }
    option["tooltip"] = {"trigger": "axis", "axisPointer": {"type": "line"}}
    return option, ds


# ── xy areas: the market diagram, curves over a numeric x with the areas between them ──

AREA_OPACITY = 0.35


@dataclass
class Curve:
    """A line through explicit (x, y) points; a step is drawn by repeating an x. A carrier
    id as `name` takes the carrier's colour (the client's), anything else `color` or the
    next Okabe-Ito colour. `legend=False` keeps a guide line out of the legend."""

    name: str
    x: list[float]
    y: list[float]
    color: str | None = None
    dashed: bool = False
    width: float = 2.0
    panel: int = 0
    legend: bool = True


@dataclass
class Area:
    """A filled region between `lower` and `upper`, both read at the points `x` (repeat an
    x for a vertical edge). The fill carries `name` in the legend, so the shading says what
    it is."""

    name: str
    x: list[float]
    lower: list[float]
    upper: list[float]
    color: str
    panel: int = 0


@dataclass
class Point:
    """A marked point (a market clearing, an equilibrium) with `label` beside it."""

    name: str
    x: float
    y: float
    label: str | None = None
    color: str | None = None
    panel: int = 0
    label_position: str = "right"


def xy_areas(
    curves: list[Curve],
    areas: list[Area] | tuple = (),
    points: list[Point] | tuple = (),
    *,
    x_name: str,
    units: list[str] | str,
    x_marks: list[dict[str, Any]] | tuple = (),
    y_marks: list[dict[str, Any]] | tuple = (),
    x_min: float | None = 0,
    x_max: float | None = None,
    y_max: list[float | None] | float | None = None,
    height: int | None = None,
) -> tuple[Option, Datasets]:
    """The textbook market diagram: curves over a numeric x with the areas between them filled.

    Every curve, area and point sits on a panel; `units` names each panel's value axis (one
    unit, one panel). Panels stack on a shared x axis (only the bottom one labelled), so a
    breakeven read off the top panel drops straight onto the bottom one: `x_marks` (dashed
    verticals, `{"value", "label"}`) run through every panel, `y_marks` (dashed horizontals,
    `{"value", "label", "panel"?}`) through one.

    An area is drawn with the stack trick, a transparent series along its lower edge and its
    depth stacked on top with a fill, so it needs no custom series. Areas come first in the
    legend, in their own colours (green for what someone gains, vermillion for what is lost
    or paid, by the `Band` convention), then the curves and points.
    """
    units = [units] if isinstance(units, str) else list(units)
    y_maxes = y_max if isinstance(y_max, list) else [y_max] * len(units)
    palette = Palette()
    datasets: Datasets = {}
    series: list[dict[str, Any]] = []
    names: list[str] = []

    def idx(panel: int) -> dict[str, Any]:
        return {"xAxisIndex": panel, "yAxisIndex": panel} if panel else {}

    for k, area in enumerate(areas):
        ds_id = f"area{k}"
        datasets[ds_id] = dataset(["x", "lower", "depth"],
                                  [[x, lo, hi - lo] for x, lo, hi in zip(area.x, area.lower, area.upper)])
        common = {"type": "line", "name": area.name, "showSymbol": False, "silent": True, "datasetId": ds_id,
                  "stack": ds_id, "stackStrategy": "all", "itemStyle": {"color": area.color}, "lineStyle": {"width": 0, "opacity": 0},
                  **idx(area.panel)}
        series.append({**common, "encode": {"x": "x", "y": "lower"}})
        series.append({**common, "encode": {"x": "x", "y": "depth"},
                       "areaStyle": {"color": area.color, "opacity": AREA_OPACITY}})
        if area.name not in names:
            names.append(area.name)

    for k, curve in enumerate(curves):
        ds_id = f"curve{k}"
        datasets[ds_id] = dataset(["x", "y"], [[x, y] for x, y in zip(curve.x, curve.y)])
        s = line_series(curve.name, ds_id, "x", palette, y="y")
        if curve.color:
            s["itemStyle"] = {"color": curve.color}
        s["lineStyle"] = {**s.get("lineStyle", {}), "width": curve.width,
                          **({"color": curve.color} if curve.color else {}),
                          **({"type": "dashed"} if curve.dashed else {})}
        s.update(idx(curve.panel))
        series.append(s)
        if curve.legend and curve.name not in names:
            names.append(curve.name)

    for j, p in enumerate(points):
        ds_id = f"point{j}"
        datasets[ds_id] = dataset(["x", "y"], [[p.x, p.y]])
        colour = p.color or cs.NEUTRAL
        series.append({
            "type": "scatter", "name": p.name, "datasetId": ds_id, "encode": {"x": "x", "y": "y"},
            "symbolSize": 12, "z": 5,
            "itemStyle": {"color": colour, "borderColor": "#ffffff", "borderWidth": 2},
            "label": {"show": bool(p.label), "formatter": p.label or "", "position": p.label_position,
                      "fontSize": 11, "fontWeight": 600, "fontFamily": "sans-serif", "color": colour},
            **idx(p.panel),
        })
        if p.name not in names:
            names.append(p.name)

    n_panels = len(units)
    # the marks hang off the first series drawn on each panel; vertical labels only on the bottom one
    first_on: dict[int, dict[str, Any]] = {}
    for s in series:
        first_on.setdefault(s.get("yAxisIndex", 0), s)
    for panel, s in first_on.items():
        data: list[dict[str, Any]] = [
            {"xAxis": m["value"], "name": m.get("label", "") if panel == n_panels - 1 else ""} for m in x_marks
        ]
        data += [{"yAxis": m["value"], "name": m.get("label", "")} for m in y_marks if m.get("panel", 0) == panel]
        if data:
            s["markLine"] = {**mark_lines([]), "data": data}

    panel_h = 200
    x_extra: dict[str, Any] = {}
    if x_min is not None:
        x_extra["min"] = x_min
    if x_max is not None:
        x_extra["max"] = x_max
    if n_panels == 1:
        grid: Any = _grid(bottom=24)
        x_axis: Any = x_value_axis(x_name, **x_extra)
        y_axis: Any = value_axis(units[0], **({"max": y_maxes[0]} if y_maxes[0] is not None else {}))
        default_height = 400
    else:
        grid, x_axis, y_axis = [], [], []
        for j, unit in enumerate(units):
            last = j == n_panels - 1
            # fixed margins, not containLabel: the panels' value labels differ in width, and the
            # x axes must line up for a mark to drop straight through them
            g = {**GRID, "left": 72, "containLabel": False, "top": GRID["top"] + j * (panel_h + PANEL_GAP)}
            if last:
                g["bottom"] = 56
            else:
                g.pop("bottom")
                g["height"] = panel_h
            grid.append(g)
            ax = {**x_value_axis(x_name if last else "", **x_extra), "gridIndex": j}
            if not last:
                ax["axisLabel"] = {"show": False}
            x_axis.append(ax)
            y_axis.append({**value_axis(unit, **({"max": y_maxes[j]} if y_maxes[j] is not None else {})),
                           "gridIndex": j})
        default_height = GRID["top"] + n_panels * panel_h + (n_panels - 1) * PANEL_GAP + 96
    option: Option = {
        "dataset": [{"id": ds_id} for ds_id in datasets],
        "tooltip": {"trigger": "item"},
        "grid": grid,
        "xAxis": x_axis,
        "yAxis": y_axis,
        "series": series,
        "legend": _legend(names),
        "_height": height or default_height,
    }
    if n_panels > 1:
        option["axisPointer"] = {"link": [{"xAxisIndex": "all"}]}
    return option, datasets


# ── region map: a hypothetical country, its subregions and the lines between them ──

REGION_IMPORTS = ["#762a83", "#af8dc3"]  # PRGn: purple where a region is short
REGION_NEUTRAL = "#ece7ef"
REGION_EXPORTS = ["#7fbf7b", "#1b7837"]  # green where it has power to spare
ARROW_COLOUR = "#0072b2"  # Okabe-Ito blue, the "plan" colour `fill_between` draws the value in
LINK_MIN_PX, LINK_MAX_PX = 3.0, 16.0
# Text sits on the coloured regions, so it is white with a soft dark shadow, legible on
# every fill and in both themes (a text box would need a backgroundColor the app refuses).
MAP_TEXT = {"color": "#ffffff", "textShadowColor": "rgba(0,0,0,0.55)", "textShadowBlur": 4, "fontSize": 11}
# Bold needs a real family: the app's charts inherit the page font ("inherit"), which a
# canvas rejects inside a bold font string, silently dropping the weight.
MAP_BOLD = {"fontWeight": 700, "fontFamily": "sans-serif"}
MAP_DARK_TEXT = "#3f3a45"  # on a region filled near the neutral middle of the scale
PALE_BELOW = 0.3  # share of the scale's reach under which a region counts as pale


@dataclass
class Region:
    """One subregion: its outline (exterior ring, (x, y) pairs), the value that colours it
    and the text shown at `label_at` (the name in bold, then `label`, one line per \\n)."""

    name: str
    polygon: list[tuple[float, float]]
    value: float | None = None
    label: str | None = None
    label_at: tuple[float, float] | None = None


@dataclass
class Site:
    """A point in the country, a plant or a city: a dot sized by `size`, coloured by
    `carrier` (a carrier id) or neutral, with `label` beside it."""

    name: str
    x: float
    y: float
    size: float
    carrier: str | None = None
    label: str | None = None
    label_position: str = "right"


@dataclass
class Link:
    """A line between two points. `capacity` sets its width (on the same MW scale as
    every other link and arrow); `flow` is signed along start -> end and moves arrows
    that way; a flow at or above the capacity draws the link vermillion (full, or
    overloaded). `outage` draws a tripped line: dashed, grey, no flow. `label` sits beside
    its middle, or at `label_at`."""

    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    capacity: float
    flow: float | None = None
    label: str | None = None
    label_at: tuple[float, float] | None = None
    outage: bool = False
    width_mw: float | None = None  # draw at this MW instead of the capacity (a flow's share, say)


@dataclass
class Arrow:
    """A broad translucent arrow for an intent rather than a wire (what a market plans to
    move, say), its width on the links' MW scale so the two compare by eye."""

    name: str
    start: tuple[float, float]
    end: tuple[float, float]
    value: float
    label: str | None = None
    label_at: tuple[float, float] | None = None


def _ring(points: list[tuple[float, float]]) -> list[list[float]]:
    ring = [[round(float(x), DECIMALS), round(float(y), DECIMALS)] for x, y in points]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _mid(a: tuple[float, float], b: tuple[float, float]) -> list[float]:
    return [round((a[0] + b[0]) / 2, DECIMALS), round((a[1] + b[1]) / 2, DECIMALS)]


def region_map(
    regions: list[Region],
    *,
    outline: list[tuple[float, float]] | None = None,
    sites: list[Site] | tuple = (),
    links: list[Link] | tuple = (),
    arrows: list[Arrow] | tuple = (),
    value_name: str,
    unit: str,
    low_label: str,
    high_label: str,
    height: int = 520,
    borders: list[list[tuple[float, float]]] | tuple = (),
    reach: float | None = None,
    map_name: str = "region",
) -> tuple[Option, Datasets]:
    """A made-up country split into subregions, for the geography behind a network effect.

    Subregions are filled on a diverging scale centred on zero (purple below, green
    above: short of power / power to spare, by default), separated by white borders,
    under the country's `outline` drawn as one strong edge. Links are wires whose width
    is their capacity, grey within it, vermillion at or above it, dashed when tripped,
    with arrows moving along the flow; an `Arrow` draws an intent on the same width
    scale. Every text is placed explicitly and drawn level, never along a line or at
    ECharts' region centres.

    `borders` are extra strong edges drawn like the outline (a boundary between groups of
    subregions, say); `reach` fixes the colour scale at plus and minus that value, so two
    maps of one country compare by colour. Two maps of one model need distinct `map_name`s,
    since the preview page registers every map under its own name.

    The GeoJSON rides in `option["_maps"]` (popped into the bundle's `maps` by
    `bundle.Figure`); coordinates are abstract, not degrees (`aspectScale` 1).
    """
    features = [
        {"type": "Feature", "properties": {"name": r.name}, "geometry": {"type": "Polygon", "coordinates": [_ring(r.polygon)]}}
        for r in regions
    ]
    xs = [p[0] for r in regions for p in r.polygon]
    ys = [p[1] for r in regions for p in r.polygon]
    pad = 0.04 * max(max(xs) - min(xs), max(ys) - min(ys))
    geo = {
        "map": map_name,
        "roam": False,
        "aspectScale": 1,
        "boundingCoords": [[min(xs) - pad, max(ys) + pad], [max(xs) + pad, min(ys) - pad]],
        "left": 8, "right": 8, "top": 8, "bottom": 64,
        "label": {"show": False},
        "itemStyle": {"borderColor": "#ffffff", "borderWidth": 2.5, "shadowBlur": 14,
                      "shadowColor": "rgba(0,0,0,0.22)", "shadowOffsetY": 3},
        "emphasis": {"disabled": True},
        "select": {"disabled": True},
        "tooltip": {"show": False},
    }
    values = [r.value for r in regions if r.value is not None]
    reach = reach or max((abs(v) for v in values), default=1.0) or 1.0
    series: list[dict[str, Any]] = [{
        "type": "map",
        "name": f"{value_name} ({unit})" if unit else value_name,
        "map": map_name,
        "geoIndex": 0,
        "data": [{"name": r.name, "value": round(float(r.value), DECIMALS)} for r in regions if r.value is not None],
    }]
    visual_map = {
        "type": "continuous",
        "seriesIndex": 0,
        "min": -round(reach, 1),
        "max": round(reach, 1),
        "orient": "horizontal",
        "left": "center",
        "bottom": 8,
        "itemWidth": 12,
        "itemHeight": 200,
        "calculable": False,
        "text": [high_label, low_label],
        "textGap": 8,
        "inRange": {"color": [REGION_IMPORTS[0], REGION_IMPORTS[1], REGION_NEUTRAL, REGION_EXPORTS[0], REGION_EXPORTS[1]]},
    }
    notes: list[dict[str, Any]] = []  # level text, drawn last by one label-only scatter

    if outline:
        series.append({
            "type": "lines", "name": "outline", "coordinateSystem": "geo", "polyline": True, "silent": True,
            "z": 3, "lineStyle": {"color": cs.NEUTRAL, "width": 2.5, "opacity": 1},
            "data": [{"coords": _ring(outline)}],
        })
    if borders:
        series.append({
            "type": "lines", "name": "borders", "coordinateSystem": "geo", "polyline": True, "silent": True,
            "z": 3, "lineStyle": {"color": cs.NEUTRAL, "width": 2.5, "opacity": 1},
            "data": [{"coords": [[round(float(x), DECIMALS), round(float(y), DECIMALS)] for x, y in b]} for b in borders],
        })

    widest = max([ln.width_mw if ln.width_mw is not None else ln.capacity for ln in links] + [a.value for a in arrows] + [1.0])
    def width(mw: float) -> float:
        return round(max(LINK_MIN_PX, LINK_MAX_PX * mw / widest), 1)

    if arrows:
        series.append({
            "type": "lines", "name": "arrows", "coordinateSystem": "geo", "silent": True, "z": 2,
            "lineStyle": {"color": ARROW_COLOUR, "opacity": 0.8, "curveness": 0},
            "data": [{"name": a.name, "coords": [list(a.start), list(a.end)],
                      "lineStyle": {"width": width(a.value)}} for a in arrows],
        })
        # the head is a rotated triangle at the tip: a lines series' own end symbol stays
        # the width of the shaft, too small to read as an arrow on a broad one
        series.append({
            "type": "scatter", "name": "arrow heads", "coordinateSystem": "geo", "silent": True, "z": 2,
            "symbol": "triangle",
            "data": [{"name": a.name, "value": list(a.end),
                      "symbolSize": [round(width(a.value) * 3.2, 1), round(width(a.value) * 2.2, 1)],
                      "symbolRotate": round(math.degrees(math.atan2(a.end[1] - a.start[1], a.end[0] - a.start[0])) - 90, 1),
                      "itemStyle": {"color": ARROW_COLOUR, "opacity": 0.8}} for a in arrows],
        })
        notes += [{"at": list(a.label_at) if a.label_at else _mid(a.start, a.end), "text": a.label, "bold": True}
                  for a in arrows if a.label]

    tripped = [ln for ln in links if ln.outage]
    if tripped:
        series.append({
            "type": "lines", "name": "tripped lines", "coordinateSystem": "geo", "silent": True, "z": 4,
            "lineStyle": {"color": cs.NEUTRAL, "opacity": 0.8, "type": "dashed", "curveness": 0},
            "data": [{"name": ln.name, "coords": [list(ln.start), list(ln.end)],
                      "lineStyle": {"width": max(2.0, width(ln.capacity) / 2)}} for ln in tripped],
        })
        notes += [{"at": list(ln.label_at) if ln.label_at else _mid(ln.start, ln.end), "text": ln.label}
                  for ln in tripped if ln.label]

    def full(ln: Link) -> bool:
        return ln.flow is not None and abs(ln.flow) >= ln.capacity * (1 - 1e-3)

    for overloaded in (False, True):
        group = [ln for ln in links if not ln.outage and full(ln) == overloaded]
        if not group:
            continue
        data = []
        for ln in group:
            a, b = (ln.start, ln.end) if (ln.flow or 0) >= 0 else (ln.end, ln.start)
            data.append({"name": ln.name, "coords": [list(a), list(b)],
                         "lineStyle": {"width": width(ln.width_mw if ln.width_mw is not None else ln.capacity)}})
            if ln.label:
                notes.append({"at": list(ln.label_at) if ln.label_at else _mid(ln.start, ln.end), "text": ln.label,
                              "bold": overloaded})
        series.append({
            "type": "lines", "name": "overloaded lines" if overloaded else "lines", "coordinateSystem": "geo",
            "silent": True, "z": 4,
            "lineStyle": {"color": BAND_ABOVE if overloaded else cs.NEUTRAL, "opacity": 1, "curveness": 0, "cap": "round"},
            "effect": {"show": True, "symbol": "arrow", "symbolSize": 7, "period": 2.5 if overloaded else 5,
                       "trailLength": 0, "color": "#ffffff"},
            "data": data,
        })

    if sites:
        biggest = max(s.size for s in sites) or 1.0
        series.append({
            "type": "scatter", "name": "sites", "coordinateSystem": "geo", "silent": True, "z": 5,
            "label": {"show": True, "position": "right", "distance": 6, **MAP_TEXT},
            "data": [{
                "name": s.name, "value": [s.x, s.y],
                "symbolSize": round(10 + 18 * math.sqrt(s.size / biggest), 1),
                "itemStyle": {"color": cs.colour(s.carrier) if s.carrier and cs.is_carrier(s.carrier) else cs.NEUTRAL,
                              "borderColor": "#ffffff", "borderWidth": 2},
                "label": {"formatter": s.label or s.name, "position": s.label_position},
            } for s in sites],
        })

    for r in regions:
        if r.label_at is not None:
            body = "".join("\n{body|" + line + "}" for line in (r.label or "").split("\n") if line)
            # a region near zero is filled almost white, where white text vanishes: dark text there
            pale = r.value is not None and abs(r.value) < PALE_BELOW * reach
            notes.append({"at": list(r.label_at), "text": "{head|" + r.name + "}" + body, "pale": pale})
    if notes:
        # rich repeated per item: an item's own label replaces the series' rich styles
        rich = {"head": {**MAP_TEXT, **MAP_BOLD, "fontSize": 13, "lineHeight": 20},
                "body": {**MAP_TEXT, "fontFamily": "sans-serif", "lineHeight": 16}}
        dark = {"color": MAP_DARK_TEXT, "textShadowBlur": 0}
        rich_pale = {k: {**v, **dark} for k, v in rich.items()}
        series.append({
            "type": "scatter", "name": "labels", "coordinateSystem": "geo", "silent": True, "z": 6,
            "symbolSize": 0,
            "label": {"show": True, "position": "inside", "lineHeight": 16, **MAP_TEXT},
            "data": [{"name": n["text"].split("\n")[0].strip("{}").split("|")[-1], "value": n["at"],
                      "label": {"formatter": n["text"], "rich": rich_pale if n.get("pale") else rich,
                                **({**MAP_BOLD, "fontSize": 12} if n.get("bold") else {})}}
                     for n in notes],
        })

    option: Option = {
        "tooltip": {"trigger": "item"},
        "geo": geo,
        "visualMap": visual_map,
        "series": series,
        "_height": height,
        "_maps": {map_name: {"type": "FeatureCollection", "features": features}},
    }
    return option, {}


# ── component schematics ──────────────────────────────────────────────────────
#
# A one-line diagram of a toy network: buses as busbars, components hung off them by
# stubs, each annotated with the attributes the card is about. The canvas is the app's
# figure width (720 px) by the figure height, and node coordinates are pixels on it: two
# invisible anchors pin the graph's bounding box to the whole canvas so ECharts' view fit
# is the identity and symbol sizes (always pixels) line up with coordinates.

DIAGRAM_WIDTH = 720
# kind -> symbol; a Bus is drawn as an edge (the busbar), not a symbol
DIAGRAM_SYMBOLS: dict[str, dict[str, Any]] = {
    "generator": {"symbol": "circle", "symbolSize": 36, "letter": "G"},
    "load": {"symbol": "triangle", "symbolSize": 26, "symbolRotate": 180},
}
BUSBAR_PX = 7
STUB_PX = 2.5
DIAGRAM_HEAD = {"fontWeight": 700, "fontSize": 12, "lineHeight": 18}
DIAGRAM_BODY = {"fontFamily": "ui-monospace, SFMono-Regular, Menlo, monospace", "fontSize": 11, "lineHeight": 16}
MUTED_OPACITY = 0.45


@dataclass
class Node:
    """One component on the diagram. `kind` picks the symbol (`DIAGRAM_SYMBOLS`) or, for a
    `bus`, a busbar from `x - width/2` to `x + width/2` at `y`. `carrier` colours the symbol
    (a carrier id, else neutral grey). `label` is the attribute text under the bold name,
    one line per `\\n`, placed to the `label_position` side; a muted (`focus=False`) node
    is drawn translucent, so the component the card explains stands out."""

    name: str
    kind: str
    x: float
    y: float
    carrier: str | None = None
    label: str | None = None
    label_position: str = "right"
    focus: bool = True
    width: float = 200.0  # bus only


@dataclass
class Edge:
    """A stub or a wire between two nodes, by name; `at` attaches an end to a bus at that
    x instead of the bus's centre."""

    a: str
    b: str
    label: str | None = None
    width: float = STUB_PX


def network_diagram(nodes: list[Node], edges: list[Edge], *, height: int = 300) -> tuple[Option, Datasets]:
    """A one-line diagram as one ECharts `graph` series with fixed node positions.

    Coordinates are pixels on a `DIAGRAM_WIDTH` x `height` canvas (origin top-left, y
    down). Buses are busbars (thick neutral edges between two invisible ends), other
    components symbols from `DIAGRAM_SYMBOLS` filled with their carrier colour, a `G` on a
    generator. An edge to a bus lands on the busbar directly below or above the other
    node. Names and attribute lines sit beside each node as label-only nodes.
    """
    by_name = {n.name: n for n in nodes}
    data: list[dict[str, Any]] = [
        {"name": "_anchor_nw", "x": 0, "y": 0, "symbolSize": 0, "label": {"show": False}},
        {"name": "_anchor_se", "x": DIAGRAM_WIDTH, "y": height, "symbolSize": 0, "label": {"show": False}},
    ]
    links: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for n in nodes:
        opacity = 1.0 if n.focus else MUTED_OPACITY
        if n.kind == "bus":
            half = n.width / 2
            data += [
                {"name": f"{n.name}:west", "x": n.x - half, "y": n.y, "symbolSize": 0, "label": {"show": False}},
                {"name": f"{n.name}:east", "x": n.x + half, "y": n.y, "symbolSize": 0, "label": {"show": False}},
            ]
            links.append({"source": f"{n.name}:west", "target": f"{n.name}:east",
                          "lineStyle": {"width": BUSBAR_PX, "color": cs.NEUTRAL, "opacity": opacity, "cap": "butt"}})
            continue
        spec = DIAGRAM_SYMBOLS[n.kind]
        colour = cs.colour(n.carrier) if n.carrier and cs.is_carrier(n.carrier) else cs.NEUTRAL
        node: dict[str, Any] = {
            "name": n.name, "x": n.x, "y": n.y,
            "symbol": spec["symbol"], "symbolSize": spec["symbolSize"],
            "itemStyle": {"color": colour, "borderColor": "#ffffff", "borderWidth": 2, "opacity": opacity},
            "label": {"show": False},
        }
        if "symbolRotate" in spec:
            node["symbolRotate"] = spec["symbolRotate"]
        if "letter" in spec:
            node["label"] = {"show": True, "position": "inside", "formatter": spec["letter"],
                             "color": "#ffffff", "fontWeight": 700, "fontSize": 15, "fontFamily": "sans-serif"}
        data.append(node)
    for n in nodes:
        head = "{head|" + n.name + "}"
        body = "".join("\n{body|" + line + "}" for line in (n.label or "").split("\n") if line)
        if n.kind == "bus":
            at = [n.x - n.width / 2, n.y + BUSBAR_PX]
            position = "bottom" if n.label_position == "bottom" else "top"
            if position == "top":
                at[1] = n.y - BUSBAR_PX
            align = "left"
        else:
            r = DIAGRAM_SYMBOLS[n.kind]["symbolSize"] / 2 + 6
            dx = {"right": r, "left": -r}.get(n.label_position, 0)
            dy = {"top": -r, "bottom": r}.get(n.label_position, 0)
            at = [n.x + dx, n.y + dy]
            position = n.label_position
            align = None
        label: dict[str, Any] = {
            "show": True, "position": position, "distance": 0, "formatter": head + body,
            "rich": {"head": DIAGRAM_HEAD, "body": DIAGRAM_BODY},
            "opacity": 1.0 if n.focus else MUTED_OPACITY + 0.2,
        }
        if align:
            label["align"] = align
        notes.append({"name": f"{n.name}:label", "x": at[0], "y": at[1], "symbolSize": 0, "label": label})
    for e in edges:
        a, b = by_name[e.a], by_name[e.b]
        ends = []
        for this, other in ((a, b), (b, a)):
            if this.kind == "bus":
                ends.append({"name": f"{this.name}@{other.name}", "x": other.x, "y": this.y, "symbolSize": 0, "label": {"show": False}})
            else:
                ends.append({"name": this.name})
        for end in ends:
            if "x" in end:
                data.append(end)
        focus = a.focus or b.focus
        link: dict[str, Any] = {
            "source": ends[0]["name"], "target": ends[1]["name"],
            "lineStyle": {"width": e.width, "color": cs.NEUTRAL, "opacity": 1.0 if focus else MUTED_OPACITY, "curveness": 0},
        }
        if e.label:
            link["label"] = {"show": True, "formatter": e.label, **DIAGRAM_BODY}
        links.append(link)
    series = {
        "type": "graph", "name": "schematic", "layout": "none",
        "roam": False, "silent": True, "animation": False, "zlevel": 0, "z": 2,
        "left": 0, "right": 0, "top": 0, "bottom": 0,
        "lineStyle": {"color": cs.NEUTRAL, "curveness": 0},
        "data": data + notes,
        "links": links,
    }
    option: Option = {"tooltip": {"show": False}, "series": [series], "_height": height}
    return option, {}
