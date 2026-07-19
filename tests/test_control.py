"""Tests for the loop control channel."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from qaymark import control


class ControlChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Path(tempfile.mkdtemp())
        (self.ws / ".harness").mkdir(parents=True, exist_ok=True)

    def test_default_is_unpaused_and_running(self) -> None:
        command = control.read_control(self.ws)
        self.assertFalse(command.paused)
        self.assertFalse(command.stop)
        self.assertIsNone(command.redirect_task)

    def test_pause_then_resume(self) -> None:
        control.pause(self.ws, note="hold")
        self.assertTrue(control.read_control(self.ws).paused)
        self.assertEqual(control.read_control(self.ws).note, "hold")
        control.resume(self.ws)
        self.assertFalse(control.read_control(self.ws).paused)

    def test_request_stop(self) -> None:
        control.request_stop(self.ws)
        self.assertTrue(control.read_control(self.ws).stop)

    def test_redirect_sets_task_and_unpauses(self) -> None:
        control.pause(self.ws)
        control.redirect(self.ws, "build a new thing")
        command = control.read_control(self.ws)
        self.assertEqual(command.redirect_task, "build a new thing")
        self.assertFalse(command.paused)
        control.clear_redirect(self.ws)
        self.assertIsNone(control.read_control(self.ws).redirect_task)

    def test_broken_control_file_falls_back_to_default(self) -> None:
        control.control_path(self.ws).write_text("{not json", encoding="utf-8")
        self.assertFalse(control.read_control(self.ws).paused)

    def test_pidfile_liveness(self) -> None:
        self.assertFalse(control.loop_is_alive(self.ws))
        control.write_pidfile(self.ws, os.getpid())
        self.assertTrue(control.loop_is_alive(self.ws))
        control.write_pidfile(self.ws, 2_147_400_000)
        self.assertFalse(control.loop_is_alive(self.ws))
        control.clear_pidfile(self.ws)
        self.assertIsNone(control.read_pidfile(self.ws))


class TurnTakingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        self.a = self.root / "alpha"
        self.b = self.root / "beta"
        (self.a / ".harness").mkdir(parents=True, exist_ok=True)
        (self.b / ".harness").mkdir(parents=True, exist_ok=True)

    def test_turn_is_exclusive(self) -> None:
        self.assertTrue(control.acquire_turn(self.a))
        self.assertFalse(control.acquire_turn(self.b))
        self.assertEqual(control.current_turn(self.a), "alpha")
        control.release_turn(self.a)
        self.assertTrue(control.acquire_turn(self.b))
        self.assertEqual(control.current_turn(self.b), "beta")

    def test_holder_can_reacquire_its_own_turn(self) -> None:
        self.assertTrue(control.acquire_turn(self.a))
        self.assertTrue(control.acquire_turn(self.a))

    def test_dead_holder_turn_is_reclaimed(self) -> None:
        turn_dir = self.root / control.TURN_LOCK
        turn_dir.mkdir()
        (turn_dir / "holder").write_text("alpha:2147400000", encoding="utf-8")
        self.assertTrue(control.acquire_turn(self.b))
        self.assertEqual(control.current_turn(self.b), "beta")


if __name__ == "__main__":
    unittest.main()
