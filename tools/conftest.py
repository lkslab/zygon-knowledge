"""Put `tools/` and the app's `src/` on sys.path so the tests import `checks`."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from validate import app_src  # noqa: E402

sys.path.insert(0, str(app_src(None)))
