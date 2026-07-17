#!/usr/bin/env python3
"""Backward-compatible entry point for the Qaymark harness.

The implementation lives in the ``qaymark`` package at the repository root.
This shim keeps the historical ``python3 scripts/code_harness.py`` invocation
working by delegating to ``qaymark.cli``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qaymark.cli import main  # noqa: E402  (path set up above)

if __name__ == "__main__":
    raise SystemExit(main())
