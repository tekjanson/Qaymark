# Job: Playable web Tetris

Build a **browser-playable** Tetris game. A human opens `index.html` from a
static server and plays with the keyboard and buttons.

The fixed acceptance tests must not be edited:

- `test_webtetris.py` — the Python state/action seam (`webtetris.py`)
- `test_game.mjs` — the browser game logic (`game.js`)

Validate with:

```bash
python3 -m unittest test_webtetris && node --test test_game.mjs && node --check app.js
```

## Files you must complete

Overwrite these two files **at the workspace root** — use exactly these paths,
do not create a `src/` folder or any subdirectory, and do not rename them:

- `game.js` — the browser game logic (a `Tetris` class plus `gameState` and
  `applyAction`), gated by `test_game.mjs`.
- `webtetris.py` — the Python seam (`game_state`, `apply_action`) over the
  seeded `tetris.py` core, gated by `test_webtetris.py`.

The acceptance tests import `webtetris` and `./game.js` from the root, so the
files must sit next to `test_webtetris.py` and `test_game.mjs`. Keep every line
at or under 100 characters and keep nesting shallow (use small helpers and early
returns), or the hygiene gate fails.

`app.js`, `index.html`, and `styles.css` are provided as an editable starter
that renders `game.js` to a canvas and wires keyboard + buttons. Keep them
working; improve them if you like.

## game.js contract (mirrors the Python core)

Export `Tetris`, `gameState`, `applyAction`, and `SHAPES`.

- `new Tetris(width = 10, height = 20, seed = 0)` — empty `board` (rows of ints,
  `board[y][x]`, `y = 0` at the top), `score = 0`, `linesCleared = 0`,
  `level = 1`, `gameOver = false`, `current = null`.
- `spawn(kind)` — place one of `I,O,T,S,Z,J,L` at the top; each piece has 4 cells
  with `min(y) === 0`; set `gameOver = true` if it cannot fit.
- `move(dx, dy)` — shift `current` if every target cell is in bounds and empty;
  return whether it moved.
- `rotate()` — rotate `current` 90 degrees clockwise about its centre cell; `O`
  never changes; return whether it rotated.
- `clearLines()` — drop full rows, pad empty rows on top, update `linesCleared`,
  `level = 1 + floor(linesCleared / 10)`, and `score` using
  `{1:100, 2:300, 3:500, 4:800}` times `level`; return the count.
- `hardDrop()` — fall until blocked, lock, clear lines, spawn the next piece.
- `tick()` — one gravity step: move down, or lock + clear + spawn when blocked.

`gameState(game)` returns `{width, height, score, level, lines, gameOver,
board}` where `board` is a fresh matrix with active-piece cells marked `2` and
locked cells `1`; the game's own board must not be mutated.

`applyAction(game, action)` maps `left`, `right`, `down`, `rotate`, and `drop`
to the methods above; any other action is a no-op.

## webtetris.py contract

`game_state(tetris)` returns the same snapshot shape (keys `width`, `height`,
`score`, `level`, `lines`, `game_over`, `board`) over the seeded `tetris.py`
core, active cells `2`, locked `1`, no mutation. `apply_action(tetris, action)`
maps `left`, `right`, `down`, `rotate`, `drop`; other actions are a no-op.

## Constraints

Everything must pass the strict slop-be-gone gate: functions small, lines <= 100
chars, a single final newline, no placeholder comments or deferred-work markers,
no eval, no debug artifacts. Every HTML button needs a `data-action` or
`onclick`. Decompose into small helpers.
