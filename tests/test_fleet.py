"""Tests for the fleet runner's deterministic helpers."""

import queue as _queue
import tempfile
import unittest
from pathlib import Path

from qaymark.config import HarnessConfig
from qaymark.fleet import _collect, _promote_winner, _worker_config


class WorkerConfigTests(unittest.TestCase):
    def test_worker_gets_own_workspace(self) -> None:
        base = HarnessConfig(task="t", workspace=Path("/tmp/base"))
        wc = _worker_config(base, 2)
        self.assertEqual(wc.workspace, Path("/tmp/base/worker-2"))
        self.assertEqual(wc.task, "t")


class CollectTests(unittest.TestCase):
    def test_first_zero_wins(self) -> None:
        q: _queue.Queue = _queue.Queue()
        q.put((0, 1))
        q.put((1, 0))
        winner, outcomes = _collect(q, 3)
        self.assertEqual(winner, 1)
        self.assertEqual(outcomes, {0: 1, 1: 0})

    def test_no_winner_when_all_fail(self) -> None:
        q: _queue.Queue = _queue.Queue()
        q.put((0, 1))
        q.put((1, 2))
        winner, outcomes = _collect(q, 2)
        self.assertIsNone(winner)
        self.assertEqual(outcomes, {0: 1, 1: 2})


class PromoteTests(unittest.TestCase):
    def test_promote_copies_winner_to_result(self) -> None:
        root = Path(tempfile.mkdtemp())
        base = HarnessConfig(task="t", workspace=root)
        (root / "worker-1").mkdir()
        (root / "worker-1" / "a.txt").write_text("hi", encoding="utf-8")
        result = _promote_winner(base, 1)
        self.assertEqual(result, root / "result")
        self.assertEqual((root / "result" / "a.txt").read_text(encoding="utf-8"), "hi")

    def test_promote_none_returns_none(self) -> None:
        base = HarnessConfig(task="t", workspace=Path(tempfile.mkdtemp()))
        self.assertIsNone(_promote_winner(base, None))


if __name__ == "__main__":
    unittest.main()
