# Job: Playable web Tetris

Build a browser-playable Tetris game in `index.html`, `app.js`, `styles.css`,
and `webtetris.py`.

The fixed acceptance tests live in `seed/test_webtetris.py` and must not be
edited. Run them with:

```bash
python3 -m unittest test_webtetris
```

## Goal

Ship a clean, human-playable Tetris UI that can be opened from a local static
server. The Python seam powers the acceptance tests; the browser game must use
the same rules and controls.

## Required files

- `webtetris.py` — state/action helpers for the tests
- `index.html` — page shell with the board, HUD, and controls
- `app.js` — browser game loop, input handling, and rendering
- `styles.css` — layout and visual polish

## Python seam

Export these helpers from `webtetris.py`:

- `game_state(tetris)` — return a JSON-friendly snapshot of the game
- `apply_action(tetris, action)` — apply one action such as `left`, `right`,
  `down`, `rotate`, `drop`, `start`, `pause`, or `restart`

The snapshot must include:

- `width`, `height`, `score`, `level`, `lines`, `game_over`
- `board` as a 20x10 matrix of ints

Use `1` for locked cells and `2` for the active falling piece. Do not mutate the
underlying board when building the snapshot.

## Browser behavior

- Arrow keys move the piece.
- ArrowUp rotates.
- Space hard-drops.
- `P` pauses and resumes.
- `R` restarts.
- The board, score, level, and lines are always visible.
- Game over is shown in the UI and the player can restart without reloading.

## Acceptance bar

The solution passes when:

- the Python seam tests pass,
- the HTML/JS/CSS files exist and wire up the playable UI,
- the code stays inside the strict hygiene gate,
- the browser game is actually usable from a local static server.

