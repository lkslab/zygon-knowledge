# SPDX-License-Identifier: MIT
"""Shared helpers for the toy models: synthetic profiles, finance, house-style
ECharts builders, the figure.json/preview writers and the runner.

Every `toymodels/<slug>/model.py` puts `toymodels/` on `sys.path` and imports from
here, so the house style and the artifact contract live in exactly one place.
"""
