#!/usr/bin/env python3
"""Which countries still need filling, derived from the data itself.

The version this replaces kept two hardcoded lists (DONE / PENDING) and a JSON
state file under work/registry_staging/. The state file is gone and the lists
had gone stale -- they named IL as pending while IL already carried a row, and
listed as pending several countries that are now well populated. A worklist that
can disagree with the data is worse than no worklist.

So there is no state file. Status is computed every time:

  done         meets the per-table floor everywhere
  in_progress  has rows, but at least one table is below its floor
  pending      no rows at all

Ordered by how far below the floor a country sits, so the emptiest go first.

Usage:
  python3 tools/worklist.py status
  python3 tools/worklist.py next --take 8        # emit the next batch as JSON
  python3 tools/worklist.py show --country SS
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "_qa"))
sys.path.insert(0, str(BASE / "tools"))

from check_registry import load, TABLES, FLOOR      # noqa: E402
from countries import WORLD, WORLD_SET              # noqa: E402


def survey():
    counts = {c: Counter() for c in WORLD}
    for t in TABLES:
        for r in load(t):
            c = r.get("country")
            if c in WORLD_SET:
                counts[c][t] += 1

    items = []
    for c in WORLD:
        n = counts[c]
        total = sum(n.values())
        deficit = {t: max(0, FLOOR[t] - n[t]) for t in TABLES}
        short = sum(deficit.values())
        status = "pending" if total == 0 else ("done" if short == 0 else "in_progress")
        items.append({"cc": c, "status": status, "rows": total, "short": short,
                      "counts": dict(n), "deficit": {k: v for k, v in deficit.items() if v}})
    # emptiest first; among equals, the ones with least data
    items.sort(key=lambda it: (-it["short"], it["rows"]))
    return items


def cmd_status(a):
    items = survey()
    c = Counter(it["status"] for it in items)
    print("status:", dict(c))
    work = [it for it in items if it["status"] != "done"]
    print(f"rows needed to bring everyone to the floor: {sum(it['short'] for it in work)}")
    by_table = Counter()
    for it in work:
        for t, d in it["deficit"].items():
            by_table[t] += d
    print("  by table:", dict(by_table))
    print("\nnext up:")
    for it in work[:12]:
        print(f"  {it['cc']}  short {it['short']:2}  have {it['counts']}  need {it['deficit']}")


def cmd_next(a):
    work = [it for it in survey() if it["status"] != "done"]
    print(json.dumps([{"cc": it["cc"], "deficit": it["deficit"],
                       "have": it["counts"]} for it in work[:a.take]], indent=2))


def cmd_show(a):
    for it in survey():
        if it["cc"] == a.country:
            print(json.dumps(it, indent=2))
            return
    sys.exit(f"{a.country} is not in the country universe")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status"); s.set_defaults(func=cmd_status)
    n = sub.add_parser("next"); n.add_argument("--take", type=int, default=8)
    n.set_defaults(func=cmd_next)
    sh = sub.add_parser("show"); sh.add_argument("--country", required=True)
    sh.set_defaults(func=cmd_show)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
