"""Tests for the local loop orchestrator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import control, orchestrator


class JobRegistryTests(unittest.TestCase):
    def test_lists_known_jobs(self) -> None:
        names = {job.name for job in orchestrator.list_jobs()}
        self.assertIn("tetris-web", names)
        self.assertIn("harness-control-room", names)

    def test_job_manifest_drives_validation(self) -> None:
        job = orchestrator.get_job("tetris-web")
        self.assertIsNotNone(job)
        assert job is not None
        self.assertIn("test_game.mjs", job.validation)
        self.assertTrue(job.task)

    def test_unknown_job_is_none(self) -> None:
        self.assertIsNone(orchestrator.get_job("does-not-exist"))


class LoopStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _make_workspace(self, name: str, phase: str) -> Path:
        workspace = self.root / name
        (workspace / ".harness").mkdir(parents=True, exist_ok=True)
        status = {"phase": phase, "attempt": 2, "max_attempts": 8, "build": 1}
        (workspace / ".harness" / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return workspace

    def test_loop_state_reports_status_and_control(self) -> None:
        workspace = self._make_workspace("demo", "watching")
        control.pause(workspace, note="held")
        state = orchestrator.loop_state(workspace, self.root)
        self.assertEqual(state["name"], "demo")
        self.assertEqual(state["phase"], "watching")
        self.assertTrue(state["paused"])
        self.assertEqual(state["note"], "held")
        self.assertFalse(state["alive"])

    def test_list_loops_discovers_all(self) -> None:
        self._make_workspace("alpha", "passed")
        self._make_workspace("beta", "attempting")
        names = {loop["name"] for loop in orchestrator.list_loops(self.root)}
        self.assertEqual(names, {"alpha", "beta"})

    def test_control_helpers_target_the_right_workspace(self) -> None:
        self._make_workspace("gamma", "watching")
        orchestrator.pause_loop("gamma", root=self.root)
        self.assertTrue(control.read_control(self.root / "gamma").paused)
        orchestrator.redirect_loop("gamma", "new task", root=self.root)
        self.assertEqual(control.read_control(self.root / "gamma").redirect_task, "new task")
        orchestrator.stop_loop("gamma", root=self.root)
        self.assertTrue(control.read_control(self.root / "gamma").stop)


class LaunchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_launch_spawns_and_registers_pid(self) -> None:
        fake = mock.Mock()
        fake.pid = 4242
        with mock.patch.object(orchestrator.subprocess, "Popen", return_value=fake) as popen:
            pid = orchestrator.launch_loop("tetris-web", root=self.root)
        self.assertEqual(pid, 4242)
        popen.assert_called_once()
        workspace = self.root / "tetris-web"
        self.assertEqual(control.read_pidfile(workspace), 4242)

    def test_launch_refuses_when_already_alive(self) -> None:
        workspace = self.root / "tetris-web"
        (workspace / ".harness").mkdir(parents=True, exist_ok=True)
        with mock.patch.object(orchestrator.control, "loop_is_alive", return_value=True):
            with self.assertRaises(RuntimeError):
                orchestrator.launch_loop("tetris-web", root=self.root)


class PendingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _mark_green(self, name: str) -> None:
        workspace = self.root / name
        (workspace / ".harness").mkdir(parents=True, exist_ok=True)
        (workspace / ".harness" / "status.json").write_text(
            json.dumps({"phase": "passed"}), encoding="utf-8"
        )

    def test_is_green_reads_passed_status(self) -> None:
        self._mark_green("tetris")
        self.assertTrue(orchestrator.is_green(self.root / "tetris"))
        self.assertFalse(orchestrator.is_green(self.root / "tetris-web"))

    def test_launch_pending_skips_green_and_runs_rest(self) -> None:
        self._mark_green("tetris")
        fake = mock.Mock()
        fake.pid = 5
        with mock.patch.object(orchestrator.subprocess, "Popen", return_value=fake):
            started = orchestrator.launch_pending(root=self.root)
        # tetris is green so it is skipped; the other jobs start.
        self.assertNotIn("tetris", started)
        self.assertIn("tetris-web", started)
        self.assertIn("harness-control-room", started)


if __name__ == "__main__":
    unittest.main()
