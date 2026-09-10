# -*- coding: utf-8 -*-
"""
QA for the pypsa-earth topics cookbook (wiring cards over Appendix A of
energy_topics/energy_modelling_demand_landscape.md).

Thin driver: all logic and the canonical rank<->slug<->title universe live in
cookbooks/_qa/topic_card_lib.py, shared with the pypsa-eur suite (before
2026-08-02 each suite carried a full copy of the checker).

Usage: python3 cookbooks/pypsa-earth/topics/_qa/check_topics.py [--registry-only]
       (from the zygon repo root)
"""

import os
import sys

QA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(
    QA_DIR, os.pardir, os.pardir, os.pardir, "_qa"))

import topic_card_lib  # noqa: E402

EXPECTED_MODEL = "pypsa-earth"
EXPECTED_REF_PREFIX = "8435f4c8"

if __name__ == "__main__":
    topic_card_lib.run(QA_DIR, EXPECTED_MODEL, EXPECTED_REF_PREFIX)
