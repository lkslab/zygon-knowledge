# SPDX-License-Identifier: MIT
"""Made-up countries for `charts.region_map`: a hand-drawn outline, smoothed, and cut
into subregions along wavy borders, each subregion picked out by a point inside it.

Coordinates are abstract (x east, y north), fixed in each model, never random, so a
rerun draws the same country. shapely comes with PyPSA.
"""

from __future__ import annotations

Point = tuple[float, float]


def country(outline: list[Point], cuts: list[list[Point]], anchors: dict[str, Point], *,
            smooth: float = 0.35) -> tuple[list[Point], dict[str, list[Point]]]:
    """The smoothed outline and, per anchor, the ring of the piece that contains it.

    Every cut is a polyline that must cross the country (extend it past the outline); the
    pieces are what the cuts leave, so neighbouring rings share their border exactly."""
    from shapely.geometry import LineString, Polygon
    from shapely.geometry import Point as P
    from shapely.ops import split

    shape = Polygon(outline).buffer(smooth, join_style="round").buffer(-smooth, join_style="round").simplify(0.03)
    pieces = [shape]
    for cut in cuts:
        line = LineString(cut)
        pieces = [g for piece in pieces for g in split(piece, line).geoms]
    rings: dict[str, list[Point]] = {}
    for name, (x, y) in anchors.items():
        piece = next(g for g in pieces if g.contains(P(x, y)))
        rings[name] = [(round(px, 3), round(py, 3)) for px, py in piece.exterior.coords]
    return [(round(px, 3), round(py, 3)) for px, py in shape.exterior.coords], rings


def inside(outline: list[Point], line: list[Point]) -> list[Point]:
    """The part of a polyline (a cut) that lies inside the country, for drawing it as a
    border: `outline` is the smoothed outline `country` returns."""
    from shapely.geometry import LineString, Polygon

    clipped = LineString(line).intersection(Polygon(outline))
    parts = list(getattr(clipped, "geoms", [clipped]))
    longest = max(parts, key=lambda g: g.length)
    return [(round(x, 3), round(y, 3)) for x, y in longest.coords]
