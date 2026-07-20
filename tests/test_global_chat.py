"""Tests for the persistent global chat, command driving, and live generation."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
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

from qaymark import chat  # noqa: E402  (module import set up above)


class DriveFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_run_all_invokes_launch_pending(self) -> None:
        with mock.patch.object(dashboard.orchestrator, "launch_pending",
                               return_value=["a", "b"]) as pending:
            summary = dashboard._drive_factory(self.root, "admin", "/run-all")
        pending.assert_called_once()
        self.assertIn("2", summary)

    def test_redirect_calls_orchestrator(self) -> None:
        with mock.patch.object(dashboard.orchestrator, "redirect_loop") as redirect:
            summary = dashboard._drive_factory(self.root, "admin", "/redirect tetris go bigger")
        redirect.assert_called_once()
        self.assertEqual(redirect.call_args[0][0], "tetris")
        self.assertIn("go bigger", summary)

    def test_unknown_command_returns_help(self) -> None:
        summary = dashboard._drive_factory(self.root, "admin", "/wat")
        self.assertIn("/launch", summary)

    def test_feedback_command_writes_to_child_workspace(self) -> None:
        (self.root / "tetris" / ".harness").mkdir(parents=True, exist_ok=True)
        summary = dashboard._drive_factory(self.root, "admin", "/feedback tetris make it pop")
        self.assertIn("tetris", summary)
        feedback = (self.root / "tetris" / ".harness" / "feedback.txt").read_text(encoding="utf-8")
        self.assertIn("make it pop", feedback)


class GlobalChatTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_command_message_drives_without_model(self) -> None:
        with mock.patch.object(dashboard.orchestrator, "launch_pending", return_value=[]):
            result = dashboard._global_chat(self.root, "admin", "/run-all")
        self.assertTrue(result["drove"])
        roles = [m["role"] for m in chat.read(self.root)]
        self.assertEqual(roles, ["operator", "system"])

    def test_plain_message_uses_model_reply(self) -> None:
        with mock.patch.object(dashboard, "ollama_chat", return_value="Try /launch tetris-web."):
            dashboard._global_chat(self.root, "admin", "what next?")
        messages = chat.read(self.root)
        self.assertEqual(messages[-1]["role"], "loop")
        self.assertIn("tetris-web", messages[-1]["text"])

    def test_offline_model_falls_back_to_command_hint(self) -> None:
        with mock.patch.object(dashboard, "ollama_chat", side_effect=OSError("down")):
            dashboard._global_chat(self.root, "admin", "help me")
        self.assertIn("offline", chat.read(self.root)[-1]["text"])


class GenerationTailTests(unittest.TestCase):
    def test_read_text_tail_limits_and_handles_missing(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.assertEqual(dashboard._read_text_tail(root / "nope.txt", 10), "")
        target = root / "gen.txt"
        target.write_text("abcdefghij", encoding="utf-8")
        self.assertEqual(dashboard._read_text_tail(target, 4), "ghij")


class GenerationStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = Path(tempfile.mkdtemp())

    def test_fresh_active_marker_reports_active(self) -> None:
        (self.artifact / "generation.txt").write_text("writing...", encoding="utf-8")
        (self.artifact / "generation.state").write_text("active", encoding="utf-8")
        status = dashboard._generation_status(self.artifact)
        self.assertTrue(status["active"])
        self.assertFalse(status["stale"])
        self.assertEqual(status["chars"], len("writing..."))

    def test_stale_active_marker_is_not_active(self) -> None:
        import os
        gen = self.artifact / "generation.txt"
        gen.write_text("half a file", encoding="utf-8")
        (self.artifact / "generation.state").write_text("active", encoding="utf-8")
        old = time.time() - 600
        os.utime(gen, (old, old))
        status = dashboard._generation_status(self.artifact)
        self.assertFalse(status["active"])
        self.assertTrue(status["stale"])

    def test_done_marker_is_idle(self) -> None:
        (self.artifact / "generation.txt").write_text("done file", encoding="utf-8")
        (self.artifact / "generation.state").write_text("done", encoding="utf-8")
        status = dashboard._generation_status(self.artifact)
        self.assertFalse(status["active"])
        self.assertFalse(status["stale"])


if __name__ == "__main__":
    unittest.main()
