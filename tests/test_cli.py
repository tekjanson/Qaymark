"""Tests for the harness CLI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qaymark.config import REPO_ROOT
from qaymark.cli import build_parser, config_from_args


class CliTests(unittest.TestCase):
    def test_forever_flag_enables_infinite_retry_mode(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        args = build_parser().parse_args(
            ["--task", "demo", "--workspace", str(tmp), "--forever"]
        )
        config = config_from_args(args)
        self.assertTrue(config.loop_forever)

    def test_rebuild_ui_target_defaults_to_free_port(self) -> None:
        makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("rebuild-ui:", makefile)
        self.assertIn('UI_PORT="$${PORT:-0}"', makefile)
        self.assertIn("make rebuild-ui", makefile)


if __name__ == "__main__":
    unittest.main()
