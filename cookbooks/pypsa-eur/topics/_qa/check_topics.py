# -*- coding: utf-8 -*-
"""
QA for the pypsa-eur topics cookbook (wiring cards over Appendix A of
energy_topics/energy_modelling_demand_landscape.md).

Thin driver: all logic and the canonical rank<->slug<->title universe live in
cookbooks/_qa/topic_card_lib.py, shared with the pypsa-earth suite (before
2026-08-02 this file was a full duplicate of earth's copy).

Usage: python3 cookbooks/pypsa-eur/topics/_qa/check_topics.py [--registry-only]
       (from the zygon repo root)
"""

import os
import sys

QA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(
    QA_DIR, os.pardir, os.pardir, os.pardir, "_qa"))

import topic_card_lib  # noqa: E402

EXPECTED_MODEL = "pypsa-eur"
EXPECTED_REF_PREFIX = "849c8858"

if __name__ == "__main__":
    topic_card_lib.run(QA_DIR, EXPECTED_MODEL, EXPECTED_REF_PREFIX)
