"""Tests for the human-in-the-loop feedback path (dashboard -> harness)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import loop
from qaymark.config import HarnessConfig

_SPEC = importlib.util.spec_from_file_location(
    "dashboard", Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
)
assert _SPEC is not None and _SPEC.loader is not None
dashboard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = dashboard
_SPEC.loader.exec_module(dashboard)

_EMPTY_PAYLOAD = json.dumps({"summary": "nothing", "operations": []})


class DashboardFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_append_and_read_feedback(self) -> None:
        workspace = self.root / "alpha"
        dashboard._append_feedback(workspace, "admin", "rewrite the layout")
        self.assertIn("rewrite the layout", dashboard._latest_feedback(workspace))

    def test_blank_feedback_is_ignored(self) -> None:
        workspace = self.root / "beta"
        dashboard._append_feedback(workspace, "admin", "   ")
        self.assertEqual(dashboard._latest_feedback(workspace), "")


class LoopFeedbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_external_feedback_is_folded_into_prompt(self) -> None:
        (self.tmp / ".harness").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".harness" / "feedback.txt").write_text("make it cleaner", encoding="utf-8")
        config = HarnessConfig(task="build a module", workspace=self.tmp, use_idud=False)
        config.max_attempts = 1
        with (
            mock.patch.object(loop, "chat", return_value=_EMPTY_PAYLOAD) as chat,
            mock.patch.object(loop, "ensure_slop_src", return_value=None),
            mock.patch.object(loop, "ensure_idud_binary", return_value=None),
        ):
            code = loop.run_harness(config)
        self.assertEqual(code, 0)
        user_prompt = chat.call_args[0][1]
        self.assertIn("make it cleaner", user_prompt)


if __name__ == "__main__":
    unittest.main()
