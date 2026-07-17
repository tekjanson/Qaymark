"""Fixed acceptance tests for the Tetris core.

This is the spec. The harness must make tetris.py pass these; it may not edit
this file. Coordinates: board[y][x], y=0 is the top row, y grows downward.
Piece cells are (x, y) tuples in absolute board coordinates.
"""

import unittest

from tetris import Tetris

KINDS = ("I", "O", "T", "S", "Z", "J", "L")


def cell_set(piece):
    return {(int(x), int(y)) for x, y in piece.cells}


class InitTests(unittest.TestCase):
    def test_default_dimensions_and_state(self):
        t = Tetris()
        self.assertEqual((t.width, t.height), (10, 20))
        self.assertEqual(t.score, 0)
        self.assertEqual(t.lines_cleared, 0)
        self.assertEqual(t.level, 1)
        self.assertFalse(t.game_over)

    def test_board_starts_empty(self):
        t = Tetris(width=6, height=8)
        self.assertEqual(len(t.board), 8)
        self.assertTrue(all(len(row) == 6 for row in t.board))
        self.assertTrue(all(cell == 0 for row in t.board for cell in row))


class SpawnTests(unittest.TestCase):
    def test_spawn_named_piece_at_top(self):
        t = Tetris()
        t.spawn("T")
        self.assertEqual(t.current.kind, "T")
        cells = cell_set(t.current)
        self.assertEqual(len(cells), 4)
        self.assertTrue(all(0 <= x < t.width and 0 <= y < t.height for x, y in cells))
        self.assertEqual(min(y for _, y in cells), 0)

    def test_all_seven_kinds_spawn_with_four_cells(self):
        for kind in KINDS:
            t = Tetris()
            t.spawn(kind)
            self.assertEqual(t.current.kind, kind)
            self.assertEqual(len(cell_set(t.current)), 4)


class MovementTests(unittest.TestCase):
    def test_move_down_shifts_all_cells(self):
        t = Tetris()
        t.spawn("O")
        before = cell_set(t.current)
        self.assertTrue(t.move(0, 1))
        self.assertEqual(cell_set(t.current), {(x, y + 1) for x, y in before})

    def test_left_wall_blocks_move(self):
        t = Tetris()
        t.spawn("O")
        while t.move(-1, 0):
            pass
        self.assertEqual(min(x for x, _ in cell_set(t.current)), 0)
        self.assertFalse(t.move(-1, 0))

    def test_floor_blocks_move(self):
        t = Tetris()
        t.spawn("O")
        while t.move(0, 1):
            pass
        self.assertEqual(max(y for _, y in cell_set(t.current)), t.height - 1)
        self.assertFalse(t.move(0, 1))

    def test_cannot_move_into_filled_cell(self):
        t = Tetris()
        t.spawn("O")
        while t.move(0, 1):
            pass
        landed = cell_set(t.current)
        for x, y in landed:
            t.board[y][x] = 1
        t.spawn("O")
        while t.move(0, 1):
            pass
        stacked = cell_set(t.current)
        self.assertTrue(landed.isdisjoint(stacked))


class RotationTests(unittest.TestCase):
    def test_o_rotation_is_noop(self):
        t = Tetris()
        t.spawn("O")
        before = cell_set(t.current)
        self.assertTrue(t.rotate())
        self.assertEqual(cell_set(t.current), before)

    def test_t_rotation_changes_cells(self):
        t = Tetris()
        t.spawn("T")
        t.move(0, 2)
        before = cell_set(t.current)
        self.assertTrue(t.rotate())
        after = cell_set(t.current)
        self.assertEqual(len(after), 4)
        self.assertNotEqual(after, before)


class LineClearTests(unittest.TestCase):
    def _fill_row(self, t, y):
        for x in range(t.width):
            t.board[y][x] = 1

    def test_clear_single_line_scores_100(self):
        t = Tetris()
        self._fill_row(t, t.height - 1)
        self.assertEqual(t.clear_lines(), 1)
        self.assertEqual(t.lines_cleared, 1)
        self.assertEqual(t.score, 100)
        self.assertTrue(all(cell == 0 for cell in t.board[t.height - 1]))

    def test_clear_two_lines_scores_300(self):
        t = Tetris()
        self._fill_row(t, t.height - 1)
        self._fill_row(t, t.height - 2)
        self.assertEqual(t.clear_lines(), 2)
        self.assertEqual(t.score, 300)

    def test_partial_row_is_not_cleared(self):
        t = Tetris()
        for x in range(t.width - 1):
            t.board[t.height - 1][x] = 1
        self.assertEqual(t.clear_lines(), 0)
        self.assertEqual(t.score, 0)

    def test_rows_above_shift_down_after_clear(self):
        t = Tetris()
        t.board[0][3] = 1
        self._fill_row(t, t.height - 1)
        t.clear_lines()
        self.assertEqual(t.board[1][3], 1)
        self.assertEqual(t.board[0][3], 0)


class DropAndOverTests(unittest.TestCase):
    def test_hard_drop_locks_four_cells(self):
        t = Tetris()
        t.spawn("O")
        t.hard_drop()
        filled = sum(1 for row in t.board for cell in row if cell != 0)
        self.assertEqual(filled, 4)
        self.assertEqual(t.lines_cleared, 0)
        self.assertFalse(t.game_over)

    def test_spawn_into_full_top_is_game_over(self):
        t = Tetris()
        for x in range(t.width):
            t.board[0][x] = 1
            t.board[1][x] = 1
        t.spawn("O")
        self.assertTrue(t.game_over)


if __name__ == "__main__":
    unittest.main()
