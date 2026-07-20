"""Fixed acceptance tests for the harness control-room project."""

from __future__ import annotations

from pathlib import Path
import unittest

from control_room import HarnessBoard


ROOT = Path(__file__).resolve().parent


class ModelTests(unittest.TestCase):
    def test_queue_adds_and_pulls_in_priority_order(self):
        board = HarnessBoard()
        board.add_project("alpha", title="Alpha", priority=1)
        board.add_project("beta", title="Beta", priority=9)
        next_project = board.pull_next()
        self.assertIsNotNone(next_project)
        self.assertEqual(next_project["id"], "beta")
        self.assertEqual(board.snapshot()["running"][0]["id"], "beta")

    def test_chat_messages_are_recorded(self):
        board = HarnessBoard()
        board.post_message("operator", "keep going")
        snapshot = board.snapshot()
        self.assertEqual(snapshot["chat"][-1]["text"], "keep going")

    def test_pause_and_resume_affect_queue_state(self):
        board = HarnessBoard()
        board.pause_queue()
        self.assertTrue(board.snapshot()["paused"])
        board.resume_queue()
        self.assertFalse(board.snapshot()["paused"])


class UiTests(unittest.TestCase):
    def test_shell_files_exist(self):
        for rel in ("index.html", "app.js", "styles.css", "control_room.py"):
            self.assertTrue((ROOT / rel).exists())

    def test_ui_shell_has_required_hooks(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        for hook in (
            'id="chat-log"',
            'id="chat-input"',
            'id="send-message"',
            'id="project-list"',
            'id="queue-list"',
            'id="pause-queue"',
            'id="resume-queue"',
            'id="status-panel"',
        ):
            self.assertIn(hook, html)


if __name__ == "__main__":
    unittest.main()
