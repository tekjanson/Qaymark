"""Tests for the operator/loop chat channel."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qaymark import chat


class ChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Path(tempfile.mkdtemp())
        (self.ws / ".harness").mkdir(parents=True, exist_ok=True)

    def test_empty_when_no_history(self) -> None:
        self.assertEqual(chat.read(self.ws), [])

    def test_post_and_read_round_trip(self) -> None:
        chat.post(self.ws, "loop", "Attempt 1: generating.")
        chat.post(self.ws, "operator", "focus on the failing test")
        messages = chat.read(self.ws)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "loop")
        self.assertEqual(messages[1]["text"], "focus on the failing test")

    def test_unknown_role_and_empty_text_are_ignored(self) -> None:
        self.assertIsNone(chat.post(self.ws, "hacker", "hi"))
        self.assertIsNone(chat.post(self.ws, "loop", "   "))
        self.assertEqual(chat.read(self.ws), [])

    def test_post_unique_dedupes_consecutive(self) -> None:
        chat.post_unique(self.ws, "system", "Waiting for my turn.")
        chat.post_unique(self.ws, "system", "Waiting for my turn.")
        self.assertEqual(len(chat.read(self.ws)), 1)
        chat.post_unique(self.ws, "system", "Rebuilding.")
        self.assertEqual(len(chat.read(self.ws)), 2)

    def test_read_limit(self) -> None:
        for index in range(10):
            chat.post(self.ws, "loop", f"msg {index}")
        recent = chat.read(self.ws, limit=3)
        self.assertEqual([m["text"] for m in recent], ["msg 7", "msg 8", "msg 9"])

    def test_corrupt_lines_are_skipped(self) -> None:
        chat.post(self.ws, "loop", "good")
        with chat.chat_path(self.ws).open("a", encoding="utf-8") as handle:
            handle.write("not json\n")
        self.assertEqual(len(chat.read(self.ws)), 1)


if __name__ == "__main__":
    unittest.main()
