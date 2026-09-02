# -*- coding: utf-8 -*-
"""Generate topics/INDEX.md from the topic cards (run after any card change).

Thin driver over cookbooks/_qa/topic_index_lib.py, shared with pypsa-earth.
"""

import os
import sys

QA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(
    QA_DIR, os.pardir, os.pardir, os.pardir, "_qa"))

import topic_index_lib  # noqa: E402

if __name__ == "__main__":
    topic_index_lib.generate(QA_DIR, "pypsa-eur")
