# Job: Tetris core

Implement a headless **Tetris core** in a single file `tetris.py` at the
workspace root. The fixed acceptance tests live in `test_tetris.py` (you may not
edit them). Run them with `python3 -m unittest test_tetris`.

## Coordinate system

- `board` is a list of `height` rows; each row is a list of `width` ints.
- Index cells as `board[y][x]`. `y = 0` is the **top** row; `y` grows downward.
- A cell value of `0` is empty; any non-zero value is filled/locked.
- Piece cells are `(x, y)` tuples in absolute board coordinates.

## Public API

Class `Tetris`:

- `__init__(self, width=10, height=20, seed=0)` — build an empty board; set
  `score=0`, `lines_cleared=0`, `level=1`, `game_over=False`, `current=None`.
- Attributes: `width`, `height`, `board`, `score`, `lines_cleared`, `level`,
  `game_over`, `current`.
- `spawn(self, kind=None)` — create a new piece at the top and set `self.current`
  (return it). `kind` is one of `"I","O","T","S","Z","J","L"`; if `None`, pick
  one (seeded). The piece must have exactly 4 cells with `min(y) == 0`. If the
  new piece overlaps a filled cell or is out of bounds, set `game_over = True`.
- `move(self, dx, dy) -> bool` — try to shift `current` by `(dx, dy)`. Return
  `True` and apply it if every target cell is in bounds and empty; otherwise
  return `False` and leave the piece unchanged.
- `rotate(self) -> bool` — rotate `current` 90° clockwise about its centre cell.
  The `"O"` piece never changes (return `True`). Return `False` if the rotated
  position is blocked, leaving the piece unchanged.
- `clear_lines(self) -> int` — remove every fully-filled row, shift the rows
  above downward, pad empty rows at the top, and return the number cleared. Add
  `count` to `lines_cleared`, set `level = 1 + lines_cleared // 10`, and add to
  `score` using the table below times `level`.
- `hard_drop(self)` — move `current` straight down until blocked, lock it into
  the board, clear lines, then spawn the next piece.
- `tick(self)` — one gravity step: move down by 1, or lock + clear + spawn if
  blocked.

`current` must expose `.kind` (str) and `.cells` (iterable of 4 `(x, y)` tuples).

## Scoring

Lines cleared in one call → base points, multiplied by `level`:
`{1: 100, 2: 300, 3: 500, 4: 800}`.

## Constraints

- Everything must pass the strict slop-be-gone gate: functions ≤ 60 lines, ≤ 5
  arguments, ≤ 4 levels of nesting, lines ≤ 100 chars, a single final newline,
  no placeholder comments, no `eval`/`exec`, no bare/broad `except`, no mutable
  default arguments. Decompose into small helper methods.
- Only create `tetris.py`. Do not modify `test_tetris.py`.
