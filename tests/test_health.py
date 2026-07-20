"""Tests for aggressive health checks and self-healing recovery."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from qaymark import health


class OllamaHealthTests(unittest.TestCase):
    def test_healthy_when_model_replies(self) -> None:
        fake = mock.MagicMock()
        fake.read.return_value = b'{"message": {"content": "OK"}}'
        ctx = mock.MagicMock()
        ctx.__enter__.return_value = fake
        with mock.patch.object(health.urllib.request, "urlopen", return_value=ctx):
            self.assertTrue(health.ollama_healthy("http://x", "m"))

    def test_unhealthy_on_timeout(self) -> None:
        with mock.patch.object(health.urllib.request, "urlopen", side_effect=OSError("timeout")):
            self.assertFalse(health.ollama_healthy("http://x", "m"))

    def test_unhealthy_on_empty_reply(self) -> None:
        fake = mock.MagicMock()
        fake.read.return_value = b'{"message": {"content": "   "}}'
        ctx = mock.MagicMock()
        ctx.__enter__.return_value = fake
        with mock.patch.object(health.urllib.request, "urlopen", return_value=ctx):
            self.assertFalse(health.ollama_healthy("http://x", "m"))


class ProgressHeartbeatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _touch_attempt(self, name: str, age: float) -> None:
        art = self.root / name / ".harness"
        art.mkdir(parents=True, exist_ok=True)
        path = art / "run-attempt-1.json"
        path.write_text("{}", encoding="utf-8")
        old = time.time() - age
        import os

        os.utime(path, (old, old))

    def test_recent_progress_true_when_fresh(self) -> None:
        self._touch_attempt("a", age=10)
        self.assertTrue(health.recent_progress(self.root, window=900))

    def test_recent_progress_false_when_stale(self) -> None:
        self._touch_attempt("a", age=5000)
        self.assertFalse(health.recent_progress(self.root, window=900))

    def test_recent_progress_true_when_nothing_ran(self) -> None:
        self.assertTrue(health.recent_progress(self.root, window=900))


class CheckLogicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def _touch(self, name: str, age: float) -> None:
        import os

        art = self.root / name / ".harness"
        art.mkdir(parents=True, exist_ok=True)
        p = art / "generation.txt"
        p.write_text("x", encoding="utf-8")
        old = time.time() - age
        os.utime(p, (old, old))

    def test_active_progress_is_healthy_without_probing(self) -> None:
        self._touch("a", age=5)
        with mock.patch.object(health, "ollama_healthy",
                               side_effect=AssertionError("probe must not run")) as probe:
            report = health.check(self.root, "http://x", "m", window=360)
        self.assertTrue(report.healthy)
        probe.assert_not_called()

    def test_stalled_and_ollama_down_is_unhealthy(self) -> None:
        self._touch("a", age=5000)
        with mock.patch.object(health, "ollama_healthy", return_value=False):
            report = health.check(self.root, "http://x", "m", window=360)
        self.assertFalse(report.healthy)

    def test_stalled_but_ollama_up_still_flags_stuck_loop(self) -> None:
        self._touch("a", age=5000)
        with mock.patch.object(health, "ollama_healthy", return_value=True):
            report = health.check(self.root, "http://x", "m", window=360)
        self.assertTrue(report.ollama_ok)
        self.assertFalse(report.progressing)
        self.assertFalse(report.healthy)


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_clear_stale_markers_marks_active_done(self) -> None:
        art = self.root / "loop" / ".harness"
        art.mkdir(parents=True, exist_ok=True)
        (art / "generation.state").write_text("active", encoding="utf-8")
        (self.root / ".turn.lock").mkdir()
        (self.root / ".turn.lock" / "holder").write_text("loop:123", encoding="utf-8")
        health._clear_stale_markers(self.root)
        self.assertEqual((art / "generation.state").read_text(encoding="utf-8"), "done")
        self.assertFalse((self.root / ".turn.lock" / "holder").exists())

    def test_recover_returns_summary(self) -> None:
        with mock.patch.object(health, "_kill_supervisors", return_value=["loop"]), \
                mock.patch.object(health.time, "sleep"):
            result = health.recover(self.root)
        self.assertEqual(result["killed"], ["loop"])
        self.assertIn("runtime", result)


if __name__ == "__main__":
    unittest.main()
