# -*- coding: utf-8 -*-
# PORTED from /home/lukas/Desktop/earth/pypsa-earth/cookbooks/data_quality/_qa/plot_matrix_maps.py (2026-07-22).
# Changes: Europe extent (bbox clip, panel limits, folium center/zoom); 32-panel
#          4x8 grid; titles say pypsa-eur / default scope.
"""
Render the data-quality MATRIX as maps of Europe: one map per registry dataset,
countries colored by grade (A green ... D red, out-of-scope grey).

Outputs (into cookbooks/data_quality/maps/):
  data_quality_maps.png   - static 32-panel grid (the at-a-glance picture)
  data_quality_maps.html  - folium map, one toggleable choropleth layer per
                            dataset (tooltip: country + grade + dataset)

Geometry: Natural Earth 110m admin-0 (vendored in _qa/), matched on ISO_A2_EH.
Micro-states absent at 110m resolution are logged, not drawn.

Usage (via the earth repo's pixi env):
  cd /home/lukas/Desktop/earth/pypsa-earth && \
  pixi run python /home/lukas/Desktop/enderpearl/pypsa-eur/cookbooks/data_quality/_qa/plot_matrix_maps.py
"""

import os

import folium
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import yaml
from matplotlib.patches import Patch

QA_DIR = os.path.dirname(os.path.abspath(__file__))
BOOK_DIR = os.path.dirname(QA_DIR)
MAPS_DIR = os.path.join(BOOK_DIR, "maps")
NE_GEOJSON = os.path.join(QA_DIR, "ne_110m_admin_0_countries.geojson")

# Europe window (lon_min, lon_max, lat_min, lat_max)
BBOX = (-25, 45, 33, 72)

GRADE_COLORS = {
    "A": "#1a9850",  # native country data
    "B": "#a6d96a",  # global/continental dataset covers (or n/a)
    "C": "#fdae61",  # silent DEFAULT/proxy fallback
    "D": "#d73027",  # absent, feature silently disappears
}
UNASSESSED = "#d9d9d9"  # outside pypsa-eur's default scope

GRADE_LABELS = {
    "A": "A - native country data",
    "B": "B - global dataset covers / n/a",
    "C": "C - silent DEFAULT/proxy fallback",
    "D": "D - absent, feature disappears",
}


def load():
    m = pd.read_csv(os.path.join(BOOK_DIR, "MATRIX.csv"), index_col=0,
                    keep_default_na=False)
    world = gpd.read_file(NE_GEOJSON)[["NAME", "ISO_A2_EH", "geometry"]]
    world = world.rename(columns={"ISO_A2_EH": "iso2"})
    world["geometry"] = world.geometry.simplify(0.02)
    world = world.cx[BBOX[0]:BBOX[1], BBOX[2]:BBOX[3]]
    missing = sorted(set(m.index) - set(world.iso2))
    if missing:
        print(f"not drawable at 110m resolution ({len(missing)}): {' '.join(missing)}")
    registry = yaml.safe_load(open(os.path.join(BOOK_DIR, "datasets.yaml")))
    titles = {d["id"]: d.get("title", d["id"]) for d in registry}
    return m, world, titles


def plot_png(m, world, titles):
    datasets = list(m.columns)
    ncols, nrows = 4, 8
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, 27))
    for ax, ds in zip(axes.flat, datasets):
        merged = world.merge(m[ds].rename("grade"), left_on="iso2",
                             right_index=True, how="left")
        merged.plot(ax=ax, color=UNASSESSED, linewidth=0)
        for grade, color in GRADE_COLORS.items():
            sub = merged[merged.grade == grade]
            if len(sub):
                sub.plot(ax=ax, color=color, linewidth=0.2, edgecolor="white")
        counts = m[ds].value_counts()
        tally = "  ".join(f"{g}:{counts.get(g, 0)}" for g in "ABCD")
        ax.set_title(f"{ds}\n{tally}", fontsize=9)
        ax.set_axis_off()
        ax.set_xlim(BBOX[0], BBOX[1])
        ax.set_ylim(BBOX[2], BBOX[3])
    for ax in axes.flat[len(datasets):]:
        ax.set_axis_off()
    handles = [Patch(color=c, label=GRADE_LABELS[g]) for g, c in GRADE_COLORS.items()]
    handles.append(Patch(color=UNASSESSED, label="outside the default scope"))
    fig.legend(handles=handles, loc="lower right", fontsize=11, frameon=False,
               bbox_to_anchor=(0.98, 0.02))
    fig.suptitle("PyPSA-Eur per-country data quality by dataset (default scope)",
                 fontsize=15, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    out = os.path.join(MAPS_DIR, "data_quality_maps.png")
    fig.savefig(out, dpi=110, bbox_inches="tight")
    print(f"wrote {out}")


def plot_folium(m, world, titles):
    fmap = folium.Map(location=[53, 12], zoom_start=4, tiles="cartodbpositron")
    for i, ds in enumerate(m.columns):
        merged = world.merge(m[ds].rename("grade"), left_on="iso2",
                             right_index=True, how="left")
        merged["grade"] = merged.grade.fillna("not assessed")
        merged["dataset"] = titles.get(ds, ds)
        layer = folium.GeoJson(
            merged.to_json(),
            name=ds,
            show=(i == 0),
            style_function=lambda feat: {
                "fillColor": GRADE_COLORS.get(
                    feat["properties"]["grade"], UNASSESSED),
                "fillOpacity": 0.85,
                "color": "white",
                "weight": 0.5,
            },
            tooltip=folium.GeoJsonTooltip(
                fields=["NAME", "grade", "dataset"],
                aliases=["country", "grade", "dataset"]),
        )
        layer.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    legend = "".join(
        f'<div><span style="background:{c};display:inline-block;width:14px;'
        f'height:14px;margin-right:6px"></span>{GRADE_LABELS[g]}</div>'
        for g, c in GRADE_COLORS.items())
    fmap.get_root().html.add_child(folium.Element(
        f'<div style="position:fixed;bottom:20px;left:20px;z-index:1000;'
        f'background:white;padding:10px;border:1px solid grey;'
        f'font-size:13px">{legend}'
        f'<div><span style="background:{UNASSESSED};display:inline-block;'
        f'width:14px;height:14px;margin-right:6px"></span>outside default scope</div>'
        f'<div style="margin-top:6px;color:#555">toggle datasets in the layer '
        f'control (top right); best viewed one layer at a time</div></div>'))
    out = os.path.join(MAPS_DIR, "data_quality_maps.html")
    fmap.save(out)
    print(f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


def main():
    os.makedirs(MAPS_DIR, exist_ok=True)
    m, world, titles = load()
    print(f"matrix: {len(m)} countries x {len(m.columns)} datasets")
    plot_png(m, world, titles)
    plot_folium(m, world, titles)


if __name__ == "__main__":
    main()
