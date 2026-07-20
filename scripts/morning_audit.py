#!/usr/bin/env python3
"""Summarise overnight factory progress from the keeper journal.

Run in the morning: ``python3 scripts/morning_audit.py``. Reads the progress
journal the keeper writes and prints the trajectory (green count over time and
each loop's build/attempt progress).
"""

import json
import os
from pathlib import Path


def _root() -> Path:
    override = os.getenv("QAYMARK_FACTORY_ROOT")
    if override:
        return Path(override).expanduser()
    base = os.getenv("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
    return Path(base) / "qaymark"


def main() -> int:
    journal = _root() / ".harness" / "progress.jsonl"
    if not journal.exists():
        print("No progress journal yet.")
        return 0
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    if not rows:
        print("Journal is empty.")
        return 0
    first, last = rows[0], rows[-1]
    print(f"Cycles recorded: {len(rows)}")
    print(f"From {first['ts']} to {last['ts']}")
    print(f"Green: {first['green']}/{first['total']} -> {last['green']}/{last['total']}")
    print("\nLatest per-loop state:")
    for row in last["loops"]:
        mark = "GREEN" if row["green"] else row["phase"]
        print(f"  {row['name']:24} build={row['build']:<4} attempt={row['attempt']} {mark}")
    builds = {row["name"]: 0 for row in last["loops"]}
    for snap in rows:
        for row in snap["loops"]:
            builds[row["name"]] = max(builds[row["name"]], row["build"])
    print("\nPeak build count per loop overnight:")
    for name, build in builds.items():
        print(f"  {name:24} {build}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
