"""Fixed acceptance tests for the web Tetris state/action seam.

The harness must make webtetris.py pass these; it may not edit this file.
"""

from __future__ import annotations

from pathlib import Path
import unittest

from tetris import Tetris
from webtetris import apply_action, game_state


ROOT = Path(__file__).resolve().parent


class StateTests(unittest.TestCase):
    def test_state_reports_all_fields(self):
        t = Tetris()
        t.spawn("O")
        s = game_state(t)
        self.assertEqual(s["width"], 10)
        self.assertEqual(s["height"], 20)
        self.assertEqual(s["score"], 0)
        self.assertEqual(s["level"], 1)
        self.assertEqual(s["lines"], 0)
        self.assertFalse(s["game_over"])
        self.assertEqual(len(s["board"]), 20)
        self.assertTrue(all(len(row) == 10 for row in s["board"]))

    def test_active_piece_marked_two(self):
        t = Tetris()
        t.spawn("O")
        s = game_state(t)
        twos = {(x, y) for y, row in enumerate(s["board"]) for x, c in enumerate(row) if c == 2}
        self.assertEqual(twos, {(int(x), int(y)) for x, y in t.current.cells})

    def test_locked_marked_one_and_board_not_mutated(self):
        t = Tetris()
        t.board[19][0] = 1
        t.spawn("O")
        s = game_state(t)
        self.assertEqual(s["board"][19][0], 1)
        self.assertTrue(all(c in (0, 1) for row in t.board for c in row))


class ActionTests(unittest.TestCase):
    def test_left_then_right_restores(self):
        t = Tetris()
        t.spawn("O")
        before = sorted(t.current.cells)
        apply_action(t, "left")
        self.assertEqual(sorted(t.current.cells), [(x - 1, y) for x, y in before])
        apply_action(t, "right")
        self.assertEqual(sorted(t.current.cells), before)

    def test_down_moves_piece(self):
        t = Tetris()
        t.spawn("O")
        before = sorted(t.current.cells)
        apply_action(t, "down")
        self.assertEqual(sorted(t.current.cells), [(x, y + 1) for x, y in before])

    def test_drop_locks_four_cells_and_respawns(self):
        t = Tetris()
        t.spawn("O")
        apply_action(t, "drop")
        filled = sum(1 for row in t.board for c in row if c != 0)
        self.assertEqual(filled, 4)
        self.assertIsNotNone(t.current)

    def test_unknown_action_is_noop(self):
        t = Tetris()
        t.spawn("O")
        before = sorted(t.current.cells)
        apply_action(t, "nope")
        self.assertEqual(sorted(t.current.cells), before)


class FrontendTests(unittest.TestCase):
    def test_browser_files_exist(self):
        for rel in ("index.html", "app.js", "styles.css"):
            self.assertTrue((ROOT / rel).exists())

    def test_ui_shell_has_required_hooks(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="board"', html)
        self.assertIn('id="score"', html)
        self.assertIn('id="level"', html)
        self.assertIn('id="lines"', html)
        self.assertIn('id="start"', html)
        self.assertIn('id="pause"', html)
        self.assertIn('id="restart"', html)


if __name__ == "__main__":
    unittest.main()
