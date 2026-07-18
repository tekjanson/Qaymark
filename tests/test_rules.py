"""Tests for the rules system and build counter (dashboard + harness)."""

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

_CLEAN_PAYLOAD = json.dumps(
    {
        "summary": "add calc",
        "operations": [
            {
                "kind": "write_file",
                "path": "calc.py",
                "lines": ['"""Calc."""', "", "", "def add(a, b):", "    return a + b"],
            }
        ],
    }
)


class DashboardRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_append_and_read_rule(self) -> None:
        ws = self.root / "alpha"
        dashboard._append_rule(ws, "admin", "always add a header comment")
        rules = dashboard._read_rules(ws)
        self.assertIn("always add a header comment", rules)
        self.assertIn("admin", rules)

    def test_blank_rule_ignored(self) -> None:
        ws = self.root / "beta"
        dashboard._append_rule(ws, "admin", "   ")
        self.assertEqual(dashboard._read_rules(ws), "")

    def test_build_count_reads_file(self) -> None:
        ws = self.root / "gamma"
        (ws / ".harness").mkdir(parents=True)
        (ws / ".harness" / "build_count").write_text("3", encoding="utf-8")
        self.assertEqual(dashboard._build_count(ws), 3)


class LoopRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_rules_folded_into_system_prompt(self) -> None:
        (self.tmp / ".harness").mkdir(parents=True, exist_ok=True)
        (self.tmp / ".harness" / "rules.md").write_text("- always use tabs", encoding="utf-8")
        config = HarnessConfig(task="build", workspace=self.tmp, use_reference=False)
        config.max_attempts = 1
        with (
            mock.patch.object(loop, "chat", return_value=_CLEAN_PAYLOAD) as chat,
            mock.patch.object(loop, "ensure_slop_src", return_value=None),
            mock.patch.object(loop, "ensure_drift_src", return_value=None),
        ):
            loop.run_harness(config)
        system_prompt = chat.call_args[0][0]
        self.assertIn("always use tabs", system_prompt)

    def test_build_count_increments_on_pass(self) -> None:
        config = HarnessConfig(task="build", workspace=self.tmp, use_reference=False)
        config.max_attempts = 1
        with (
            mock.patch.object(loop, "chat", return_value=_CLEAN_PAYLOAD),
            mock.patch.object(loop, "ensure_slop_src", return_value=None),
            mock.patch.object(loop, "ensure_drift_src", return_value=None),
        ):
            loop.run_harness(config)
        self.assertEqual(loop._read_build_count(config), 1)
        status = json.loads((self.tmp / ".harness" / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["build"], 1)


if __name__ == "__main__":
    unittest.main()
