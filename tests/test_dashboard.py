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
        self.assertEqual(data["floor"]["phases"][0], "starting")
        self.assertEqual(len(data["floor"]["nodes"]), 2)


class FloorReadabilityTests(unittest.TestCase):
    """The floor must be human-readable; this pins down what that means."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _floor(self, phases: list[str]) -> dict:
        for index, phase in enumerate(phases):
            workspace = self.root / f"ws{index}"
            (workspace / ".harness").mkdir(parents=True, exist_ok=True)
            status = {"phase": phase, "attempt": 1, "max_attempts": 3}
            (workspace / ".harness" / "status.json").write_text(
                json.dumps(status), encoding="utf-8"
            )
        return dashboard.overview(self.root, "admin")["floor"]

    def test_generated_floor_is_readable(self) -> None:
        floor = self._floor(["attempting", "watching", "passed"])
        self.assertTrue(dashboard.floor_is_readable(floor))

    def test_every_phase_maps_to_a_station(self) -> None:
        floor = self._floor(["paused", "reverted", "stopped", "idle"])
        for node in floor["nodes"]:
            self.assertIn(node["station"], floor["phases"])
        self.assertTrue(dashboard.floor_is_readable(floor))

    def test_no_two_loops_share_a_row(self) -> None:
        floor = self._floor(["watching", "watching", "watching"])
        rows = [node["row"] for node in floor["nodes"]]
        self.assertEqual(len(rows), len(set(rows)))

    def test_drunk_floor_is_rejected(self) -> None:
        drunk = {
            "phases": list(dashboard.PHASE_ORDER),
            "tilt": 68,
            "skew": -18,
            "nodes": [{"col": 0, "row": 0, "progress": 0.5}],
        }
        self.assertFalse(dashboard.floor_is_readable(drunk))

    def test_out_of_bounds_node_is_rejected(self) -> None:
        bad = {
            "phases": list(dashboard.PHASE_ORDER),
            "tilt": 48,
            "skew": 0,
            "nodes": [{"col": 99, "row": 0, "progress": 2.0}],
        }
        self.assertFalse(dashboard.floor_is_readable(bad))

    def test_overlapping_rows_are_rejected(self) -> None:
        overlap = {
            "phases": list(dashboard.PHASE_ORDER),
            "tilt": 48,
            "skew": 0,
            "nodes": [
                {"col": 0, "row": 0, "progress": 0.1},
                {"col": 1, "row": 0, "progress": 0.2},
            ],
        }
        self.assertFalse(dashboard.floor_is_readable(overlap))


class LoopControlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _make_loop(self, name: str) -> Path:
        workspace = self.root / name
        (workspace / ".harness").mkdir(parents=True, exist_ok=True)
        status = {"phase": "watching", "attempt": 1, "max_attempts": 3}
        (workspace / ".harness" / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return workspace

    def test_loops_payload_lists_jobs_and_loops(self) -> None:
        self._make_loop("demo")
        payload = dashboard._loops_payload(self.root)
        self.assertTrue(any(loop["name"] == "demo" for loop in payload["loops"]))
        self.assertTrue(payload["jobs"])

    def test_apply_loop_control_pause_and_redirect(self) -> None:
        workspace = self._make_loop("demo")
        dashboard._apply_loop_control(self.root, {"name": "demo", "action": "pause"})
        from qaymark import control

        self.assertTrue(control.read_control(workspace).paused)
        dashboard._apply_loop_control(
            self.root, {"name": "demo", "action": "redirect", "task": "do X"}
        )
        self.assertEqual(control.read_control(workspace).redirect_task, "do X")

    def test_apply_loop_control_rejects_bad_action(self) -> None:
        self._make_loop("demo")
        with self.assertRaises(ValueError):
            dashboard._apply_loop_control(self.root, {"name": "demo", "action": "nope"})


class BindServerTests(unittest.TestCase):
    """`make up` must not crash when its port is already in use."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _handler(self):
        from functools import partial

        return partial(dashboard.DashboardHandler, root=self.root)

    def test_busy_port_falls_back_to_a_free_port(self) -> None:
        import socket

        taken = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        busy = taken.getsockname()[1]
        try:
            server = dashboard._bind_server(self._handler(), busy)
        finally:
            taken.close()
        try:
            self.assertNotEqual(server.server_address[1], busy)
            self.assertGreater(server.server_address[1], 0)
        finally:
            server.server_close()

    def test_free_port_is_used_directly(self) -> None:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            free = probe.getsockname()[1]
        server = dashboard._bind_server(self._handler(), free)
        try:
            self.assertEqual(server.server_address[1], free)
        finally:
            server.server_close()


class ConsoleShellTests(unittest.TestCase):
    def test_console_shell_exposes_plan_and_control_state(self) -> None:
        self.assertIn('id="loop-state"', dashboard.CONSOLE_SHELL)
        self.assertIn('id="plan-meta"', dashboard.CONSOLE_SHELL)


if __name__ == "__main__":
    unittest.main()
