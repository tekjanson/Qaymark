"""Tests for the around-the-clock supervisor (feedback-driven rebuilds)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qaymark import factory
from qaymark.config import HarnessConfig


def _config(tmp: Path) -> HarnessConfig:
    config = HarnessConfig(task="demo", workspace=tmp, use_idud=False)
    config.max_attempts = 1
    return config


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_snapshot_and_restore_round_trip(self) -> None:
        (self.tmp / "keep.py").write_text("good = 1\n", encoding="utf-8")
        snapshot = factory._snapshot_files(self.tmp)
        (self.tmp / "keep.py").write_text("broken = 2\n", encoding="utf-8")
        (self.tmp / "extra.py").write_text("junk = 3\n", encoding="utf-8")
        factory._restore_files(self.tmp, snapshot)
        self.assertEqual((self.tmp / "keep.py").read_text(encoding="utf-8"), "good = 1\n")
        self.assertFalse((self.tmp / "extra.py").exists())


class SupervisorLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".harness").mkdir(parents=True, exist_ok=True)

    def _write_feedback(self, text: str) -> None:
        (self.tmp / ".harness" / "feedback.txt").write_text(text, encoding="utf-8")

    def test_initial_build_only_when_no_feedback(self) -> None:
        config = _config(self.tmp)
        with mock.patch.object(factory, "run_harness", return_value=0) as run:
            result = factory.supervise(config, max_cycles=1)
        run.assert_called_once()
        self.assertEqual(result.cycles, 0)
        self.assertTrue(result.passed)

    def test_new_feedback_triggers_rebuild(self) -> None:
        config = _config(self.tmp)
        # No feedback exists at initial build; new feedback then arrives during
        # the watch loop, which must trigger exactly one rebuild.
        signatures = ["", "this sucks, rewrite it", "this sucks, rewrite it"]
        with (
            mock.patch.object(factory, "run_harness", return_value=0) as run,
            mock.patch.object(factory, "_feedback_signature", side_effect=signatures),
        ):
            result = factory.supervise(config, max_cycles=1)
        # one initial build + one feedback-driven rebuild
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result.cycles, 1)

    def test_preexisting_feedback_is_not_replayed(self) -> None:
        config = _config(self.tmp)
        self._write_feedback("old complaint already handled")
        with mock.patch.object(factory, "run_harness", return_value=0) as run:
            result = factory.supervise(config, max_cycles=1)
        # feedback present before the build is consumed by it, not replayed
        run.assert_called_once()
        self.assertEqual(result.cycles, 0)

    def test_failed_rebuild_rolls_back(self) -> None:
        config = _config(self.tmp)
        (self.tmp / "app.py").write_text("v = 1\n", encoding="utf-8")

        def _bad_run(_config: HarnessConfig) -> int:
            (self.tmp / "app.py").write_text("v = 999\n", encoding="utf-8")
            return 1

        with mock.patch.object(factory, "run_harness", side_effect=_bad_run):
            code = factory._rerun_with_rollback(config)
        self.assertEqual(code, 1)
        self.assertEqual((self.tmp / "app.py").read_text(encoding="utf-8"), "v = 1\n")


if __name__ == "__main__":
    unittest.main()
