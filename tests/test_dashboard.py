"""Tests for the signed-in control plane dashboard."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SPEC = importlib.util.spec_from_file_location(
    "dashboard", Path(__file__).resolve().parent.parent / "scripts" / "dashboard.py"
)
assert _SPEC is not None and _SPEC.loader is not None
dashboard = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = dashboard
_SPEC.loader.exec_module(dashboard)


class DashboardAuthTests(unittest.TestCase):
    def test_token_roundtrip(self) -> None:
        env = {"DASHBOARD_PASSWORD": "secret", "DASHBOARD_USER": "admin"}
        with mock.patch.dict(os.environ, env):
            token = dashboard._token("admin")
            self.assertEqual(dashboard._verify_token(token), "admin")


class DashboardOverviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _write_status(
        self, rel: str, phase: str, attempt: int, validation: bool, hygiene: bool
    ) -> None:
        workspace = self.root / rel
        (workspace / ".harness").mkdir(parents=True, exist_ok=True)
        status = {
            "phase": phase,
            "attempt": attempt,
            "max_attempts": 3,
            "validation_ok": validation,
            "hygiene_passed": hygiene,
        }
        (workspace / ".harness" / "status.json").write_text(json.dumps(status), encoding="utf-8")
        attempt_file = workspace / ".harness" / "run-attempt-1.json"
        attempt_file.write_text(json.dumps({"summary": f"{rel} summary"}), encoding="utf-8")

    def test_discovers_nested_workspaces(self) -> None:
        self._write_status("alpha", "passed", 1, True, True)
        self._write_status("nested/beta", "retrying", 2, False, True)
        workspaces = dashboard._discover_workspaces(self.root)
        found = {p.relative_to(self.root).as_posix() for p in workspaces}
        self.assertEqual(found, {"alpha", "nested/beta"})

    def test_overview_counts_and_links(self) -> None:
        self._write_status("alpha", "passed", 1, True, True)
        self._write_status("beta", "failed", 3, False, False)
        data = dashboard.overview(self.root, "admin")
        self.assertEqual(data["counts"]["total"], 2)
        self.assertEqual(data["counts"]["passed"], 1)
        self.assertEqual(data["counts"]["failed"], 1)
        self.assertEqual(data["workspaces"][0]["link"], "/workspace/alpha")


if __name__ == "__main__":
    unittest.main()
