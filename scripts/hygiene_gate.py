#!/usr/bin/env python3
"""Repository hygiene gate.

Runs the real slop-be-gone (sbg) engine with the strict Qaymark manifest so
every commit and CI run must clear the same fractal-consistency rules that the
harness enforces on generated code. Exits non-zero when violations exist, and
fails closed if the gate cannot be provisioned.

Used by both the pre-commit hook and CI.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qaymark.config import DEFAULT_MANIFEST, default_cache_dir  # noqa: E402
from qaymark.references import ensure_slop_src  # noqa: E402


def build_command(root: Path, manifest: Path, staged: bool) -> list[str]:
    cmd = ["python3", "-m", "sbg.cli", "check", str(root), "--strict"]
    cmd += ["--manifest", str(manifest)]
    if staged:
        cmd.append("--staged")
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the strict slop-be-gone hygiene gate.")
    parser.add_argument("--staged", action="store_true", help="Only scan git-staged files")
    parser.add_argument("--path", default=".", help="Repository root to scan")
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    src = ensure_slop_src(default_cache_dir())
    if src is None:
        print("hygiene gate: could not provision slop-be-gone; failing closed.", file=sys.stderr)
        return 1

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(src), env.get("PYTHONPATH", "")]))
    command = build_command(root, DEFAULT_MANIFEST, args.staged)
    result = subprocess.run(command, env=env, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
