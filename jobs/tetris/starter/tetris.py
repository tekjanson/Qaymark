"""Headless Tetris core — starter scaffold.

Fill in every method marked NotImplementedError so that `test_tetris.py` passes.
Coordinates: board[y][x], y=0 is the top row, y grows downward. Piece cells are
absolute (x, y) tuples. Keep every method small and every line <= 100 chars.
"""

from __future__ import annotations

import random

SHAPES = {
    "I": [(0, 1), (1, 1), (2, 1), (3, 1)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(1, 0), (0, 1), (1, 1), (2, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)],
}
SCORE_TABLE = {1: 100, 2: 300, 3: 500, 4: 800}


class Piece:
    def __init__(self, kind, cells):
        self.kind = kind
        self.cells = cells


class Tetris:
    def __init__(self, width=10, height=20, seed=0):
        self.width = width
        self.height = height
        self.board = [[0] * width for _ in range(height)]
        self.score = 0
        self.lines_cleared = 0
        self.level = 1
        self.game_over = False
        self.current = None
        self._rng = random.Random(seed)

    def _shape(self, kind):
        """Return the four (x, y) cells for kind, shifted near centre, min y == 0."""
        raise NotImplementedError()

    def _in_bounds(self, x, y):
        """Return True if (x, y) is a valid cell inside the board."""
        raise NotImplementedError()

    def _fits(self, cells):
        """Return True if every cell is in bounds (use _in_bounds) and empty on board."""
        raise NotImplementedError()

    def _center(self, cells):
        """Return the (x, y) pivot cell that rotation turns around."""
        raise NotImplementedError()

    def spawn(self, kind=None):
        """Create a piece at the top, set self.current, set game_over if it cannot fit."""
        raise NotImplementedError()

    def move(self, dx, dy):
        """Shift current by (dx, dy) if it fits; return whether it moved."""
        raise NotImplementedError()

    def rotate(self):
        """Rotate current clockwise about self._center; O is a no-op; return success."""
        raise NotImplementedError()

    def _lock(self):
        """Write the current piece's cells into the board."""
        raise NotImplementedError()

    def _full_rows(self):
        """Return the list of y indices whose row is completely filled."""
        return [y for y in range(self.height) if all(self.board[y])]

    def _points(self, count):
        """Return the score for clearing count rows (SCORE_TABLE times level)."""
        return SCORE_TABLE.get(count, 800) * self.level

    def clear_lines(self):
        """Clear full rows, shift the rest down, update score, return the count."""
        full = self._full_rows()
        count = len(full)
        if count == 0:
            return 0
        kept = [row for i, row in enumerate(self.board) if i not in full]
        self.board = [[0] * self.width for _ in range(count)] + kept
        self.lines_cleared += count
        self.level = 1 + self.lines_cleared // 10
        self.score += self._points(count)
        return count

    def hard_drop(self):
        """Move down until blocked, lock, clear lines, then spawn the next piece."""
        raise NotImplementedError()

    def tick(self):
        """One gravity step: move down, or lock + clear + spawn when blocked."""
        raise NotImplementedError()
