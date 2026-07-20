#!/usr/bin/env python3
"""CLI entry point for the forever-keeper.

Keeps the factory working and audits when everything is green. See
``qaymark.keeper`` for the implementation.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qaymark import keeper  # noqa: E402  (path set up above)
from qaymark.config import factory_root  # noqa: E402  (path set up above)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep the Qaymark factory working forever")
    parser.add_argument("--root", default=None, help="Factory root to watch")
    parser.add_argument("--interval", type=float, default=20.0, help="Seconds between cycles")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    args = parser.parse_args(argv)
    root = Path(args.root).expanduser() if args.root else factory_root()
    if args.once:
        plan = keeper.keep_once(root.resolve())
        print(f"keeper: pending={plan.pending} all_green={plan.all_green}", flush=True)
        return 0
    return keeper.run_forever(root, interval=args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
