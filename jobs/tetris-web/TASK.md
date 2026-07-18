# Job: Playable web Tetris

Build the browser game logic in a single file **`game.js`** at the workspace
root. A human opens `index.html` from a static server and plays with the
keyboard and buttons; `app.js` renders your `game.js` to a canvas.

## What to do

Complete **`game.js` only** — overwrite it at the workspace root (do not create
a `src/` folder, do not rename it). Every other file is already provided:

- `test_game.mjs` — the fixed Node acceptance tests for `game.js` (do not edit).
- `app.js`, `index.html`, `styles.css` — the browser shell that uses `game.js`.
- `webtetris.py`, `tetris.py`, `test_webtetris.py` — a separate Python seam,
  already complete. Ignore them; do not touch them.

Validate your `game.js` with:

```bash
node --test test_game.mjs && node --check app.js
```

## game.js contract

This is plain browser JavaScript (ES module, camelCase). Export `Tetris`,
`gameState`, `applyAction`, and `SHAPES`.

- `new Tetris(width = 10, height = 20, seed = 0)` — `board` is `height` rows of
  `width` ints (`board[y][x]`, `y = 0` at the top); `score = 0`,
  `linesCleared = 0`, `level = 1`, `gameOver = false`, `current = null`.
- `spawn(kind)` — place one of `I,O,T,S,Z,J,L` at the top; the piece has 4 cells
  with `min(y) === 0`; set `gameOver = true` if it cannot fit; else set
  `current` (an object with `.kind` and `.cells`, an array of `[x, y]` pairs).
- `move(dx, dy)` — shift `current` if every target cell is in bounds and the
  board is empty there; return whether it moved.
- `rotate()` — rotate `current` 90 degrees clockwise about its centre cell;
  `"O"` never changes (return true); return whether it rotated.
- `clearLines()` — remove full rows, pad empty rows on top, update
  `linesCleared`, `level = 1 + Math.floor(linesCleared / 10)`, and `score` using
  `{1:100, 2:300, 3:500, 4:800}` times `level`; return the count.
- `hardDrop()` — move down until blocked, lock the piece (board cells become 1),
  clear lines, then spawn the next piece.
- `tick()` — one gravity step: move down, or lock + clear + spawn when blocked.

`gameState(game)` returns `{width, height, score, level, lines, gameOver,
board}` where `board` is a fresh copy with active-piece cells set to `2` and
locked cells `1`; the game's own board must not be mutated.

`applyAction(game, action)` maps `"left"`, `"right"`, `"down"`, `"rotate"`, and
`"drop"` to the methods above; any other action is a no-op.

## Style constraints (strict hygiene gate)

Keep every line at or under 100 characters, keep functions small and nesting
shallow (use small helpers and early returns), end the file with a single
newline, and use no placeholder comments, no deferred-work markers, and no
`eval`. Follow the structure already sketched in the `game.js` starter.
