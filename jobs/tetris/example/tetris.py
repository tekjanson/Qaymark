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
        random.seed(seed)
        self.width = width
        self.height = height
        self.board = [[0] * width for _ in range(height)]
        self.score = 0
        self.lines_cleared = 0
        self.level = 1
        self.game_over = False
        self.current = None

    def spawn(self, kind=None):
        if kind is None:
            kind = random.choice(list(SHAPES.keys()))
        cells = SHAPES[kind]
        min_y = min(y for _, y in cells)
        offset = (self.width - len(cells)) // 2
        new_cells = [(x + offset, y - min_y) for x, y in cells]
        if not self._fits(new_cells):
            self.game_over = True
            return None
        self.current = Piece(kind, new_cells)
        return self.current

    def _shape(self, kind):
        cells = SHAPES[kind]
        min_y = min(y for _, y in cells)
        offset = (self.width - len(cells)) // 2
        return [(x + offset, y - min_y) for x, y in cells]

    def _fits(self, cells):
        return all(
            0 <= x < self.width and 0 <= y < self.height and self.board[y][x] == 0 for x, y in cells
        )

    def move(self, dx, dy) -> bool:
        new_cells = [(x + dx, y + dy) for x, y in self.current.cells]
        if self._fits(new_cells):
            self.current.cells = new_cells
            return True
        return False

    def rotate(self) -> bool:
        kind = self.current.kind
        if kind == "O":
            return True
        center_x, center_y = (
            sum(x for x, _ in self.current.cells) // 4,
            sum(y for _, y in self.current.cells) // 4,
        )
        new_cells = [
            (center_x + (y - center_y), center_y - (x - center_x)) for x, y in self.current.cells
        ]
        if self._fits(new_cells):
            self.current.cells = new_cells
            return True
        return False

    def _full_rows(self) -> list[int]:
        return [y for y, row in enumerate(self.board) if all(cell != 0 for cell in row)]

    def clear_lines(self) -> int:
        full_rows = self._full_rows()
        count = len(full_rows)
        if count > 0:
            self.board = [row for y, row in enumerate(self.board) if y not in full_rows]
            self.board = [[0] * self.width for _ in range(count)] + self.board
            self.score += SCORE_TABLE[count] * self.level
            self.lines_cleared += count
            self.level = 1 + self.lines_cleared // 10
        return count

    def hard_drop(self):
        while self.move(0, 1):
            pass
        self._lock()
        self.clear_lines()
        self.spawn()

    def _lock(self):
        for x, y in self.current.cells:
            self.board[y][x] = 1

    def tick(self):
        if not self.move(0, 1):
            self._lock()
            self.clear_lines()
            self.spawn()
