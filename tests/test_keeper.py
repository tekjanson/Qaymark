"""Tests for escaped-newline repair and the forever-keeper planning."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import keeper, operations


class ConcurrencyCapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_keep_once_launches_only_up_to_cap(self) -> None:
        loops = {}  # nothing alive yet
        jobs = [mock.Mock(name="j1"), mock.Mock(name="j2"), mock.Mock(name="j3")]
        for i, job in enumerate(jobs):
            job.name = f"job{i}"
        launched = []
        with mock.patch.dict("os.environ", {"QAYMARK_MAX_ACTIVE_LOOPS": "1"}), \
                mock.patch.object(keeper.orchestrator, "list_jobs", return_value=jobs), \
                mock.patch.object(keeper, "_loops_by_name", return_value=loops), \
                mock.patch.object(keeper.orchestrator, "launch_loop",
                                  side_effect=lambda name, **k: launched.append(name)), \
                mock.patch.object(keeper.chat, "post"):
            keeper.keep_once(self.root)
        self.assertEqual(len(launched), 1)

    def test_active_loop_uses_a_slot(self) -> None:
        loops = {"job0": {"alive": True, "green": False}}
        jobs = [mock.Mock()]
        jobs[0].name = "job0"
        launched = []
        with mock.patch.dict("os.environ", {"QAYMARK_MAX_ACTIVE_LOOPS": "1"}), \
                mock.patch.object(keeper.orchestrator, "list_jobs", return_value=jobs), \
                mock.patch.object(keeper, "_loops_by_name", return_value=loops), \
                mock.patch.object(keeper.orchestrator, "launch_loop",
                                  side_effect=lambda name, **k: launched.append(name)), \
                mock.patch.object(keeper.chat, "post"):
            keeper.keep_once(self.root)
        self.assertEqual(launched, [])


class HealthCycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_healthy_resets_streak(self) -> None:
        ok = keeper.health.HealthReport(ollama_ok=True, progressing=True, detail="ok")
        with mock.patch.object(keeper.health, "check", return_value=ok):
            self.assertEqual(keeper.health_cycle(self.root, 5), 0)

    def test_unhealthy_increments_then_recovers(self) -> None:
        bad = keeper.health.HealthReport(ollama_ok=False, progressing=False, detail="down")
        with mock.patch.dict("os.environ", {"QAYMARK_UNHEALTHY_LIMIT": "2"}), \
                mock.patch.object(keeper.health, "check", return_value=bad), \
                mock.patch.object(keeper.chat, "post"), \
                mock.patch.object(keeper.health, "recover",
                                  return_value={"killed": [], "runtime": "x"}) as rec:
            streak = keeper.health_cycle(self.root, 0)
            self.assertEqual(streak, 1)
            rec.assert_not_called()
            streak = keeper.health_cycle(self.root, streak)
            self.assertEqual(streak, 0)
            rec.assert_called_once()


class EscapedNewlineTests(unittest.TestCase):
    def test_single_line_with_escaped_newlines_is_repaired(self) -> None:
        op = {"kind": "write_file", "path": "a.py", "content": "def f():\\n    return 1"}
        body = operations._content_from_operation(op)
        self.assertEqual(body, "def f():\n    return 1")

    def test_real_newlines_are_left_alone(self) -> None:
        op = {"kind": "write_file", "path": "a.py", "lines": ["def f():", "    return 1"]}
        self.assertEqual(operations._content_from_operation(op), "def f():\n    return 1\n")

    def test_apply_writes_valid_multiline_file(self) -> None:
        root = Path(tempfile.mkdtemp())
        payload = {"operations": [
            {"kind": "write_file", "path": "m.py", "content": "x = 1\\ny = 2\\n"}]}
        operations.apply_operations(root, payload)
        text = (root / "m.py").read_text(encoding="utf-8")
        self.assertIn("x = 1\n", text)
        self.assertIn("y = 2", text)
        self.assertNotIn("\\n", text)


class KeeperJournalTests(unittest.TestCase):
    def test_snapshot_counts_green_and_records_rows(self) -> None:
        loops = {"a": {"green": True, "build": 2, "phase": "passed"},
                 "b": {"green": False, "build": 0, "phase": "attempting"}}
        snap = keeper.journal_snapshot(loops, ["a", "b"])
        self.assertEqual(snap["green"], 1)
        self.assertEqual(snap["total"], 2)
        names = {row["name"] for row in snap["loops"]}
        self.assertEqual(names, {"a", "b"})


class KeeperPlanTests(unittest.TestCase):
    def test_pending_skips_green_alive_and_paused(self) -> None:
        loops = {
            "green": {"green": True, "alive": False},
            "running": {"green": False, "alive": True},
            "paused": {"green": False, "alive": False, "paused": True},
            "stopping": {"green": False, "alive": False, "stopping": True},
            "backlog": {"green": False, "alive": False},
        }
        names = list(loops.keys()) + ["never-seen"]
        self.assertEqual(keeper.pending_jobs(loops, names), ["backlog", "never-seen"])

    def test_all_green_yields_audit(self) -> None:
        loops = {"a": {"green": True, "build": 3, "attempt": 2},
                 "b": {"green": True, "build": 1, "attempt": 1}}
        plan = keeper.make_plan(loops, ["a", "b"])
        self.assertTrue(plan.all_green)
        self.assertEqual(plan.pending, [])
        self.assertIn("every job is green", plan.audit)
        self.assertIn("a: green on build 3", plan.audit)

    def test_not_all_green_has_no_audit(self) -> None:
        loops = {"a": {"green": True}, "b": {"green": False, "alive": False}}
        plan = keeper.make_plan(loops, ["a", "b"])
        self.assertFalse(plan.all_green)
        self.assertIsNone(plan.audit)
        self.assertIn("b", plan.pending)


if __name__ == "__main__":
    unittest.main()
