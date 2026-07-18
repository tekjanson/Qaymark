#!/usr/bin/env python3
"""Launch a built workspace as a playable game — but only if it passes.

Validates the workspace with its acceptance command first, refuses to serve a
broken build, then serves the static site on a free port and prints the URL.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qaymark.serve import find_free_port, has_entrypoint, serve, validate  # noqa: E402


def _default_validation(workspace: Path) -> str:
    if (workspace / "test_game.mjs").exists():
        return "node --test test_game.mjs && node --check app.js"
    return "true"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve a built workspace if it passes.")
    parser.add_argument("workspace", help="workspace directory to serve")
    parser.add_argument("--port", type=int, default=8800, help="preferred port")
    parser.add_argument("--entrypoint", default="index.html", help="page to open")
    parser.add_argument("--validation-command", default=None, help="override the gate command")
    parser.add_argument("--skip-validation", action="store_true", help="serve without checking")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    if not has_entrypoint(workspace, args.entrypoint):
        print(f"no {args.entrypoint} in {workspace}; nothing to serve", file=sys.stderr)
        return 2

    if not args.skip_validation:
        command = args.validation_command or _default_validation(workspace)
        result = validate(workspace, command)
        if result.returncode != 0:
            print("refusing to serve: the build does not pass yet.", file=sys.stderr)
            print((result.stdout + result.stderr)[:1200], file=sys.stderr)
            return 1
        print("✅ build passes; launching.", flush=True)

    port = find_free_port(args.port)
    serve(workspace, port, args.entrypoint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
