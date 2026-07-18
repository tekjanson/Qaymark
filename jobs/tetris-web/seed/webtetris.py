"""Python state/action seam over the seeded Tetris core.

This adapter is provided complete; the harness focuses on building game.js. It
exposes the same snapshot/action shape as the browser game so test_webtetris.py
gates the Python side.
"""

from __future__ import annotations

from tetris import Tetris

_ACTIONS = {
    "left": lambda t: t.move(-1, 0),
    "right": lambda t: t.move(1, 0),
    "down": lambda t: t.move(0, 1),
    "rotate": lambda t: t.rotate(),
    "drop": lambda t: t.hard_drop(),
}


def game_state(tetris: Tetris) -> dict:
    """Return a JSON-friendly snapshot; active cells are 2, locked cells 1."""

    board = [row[:] for row in tetris.board]
    if tetris.current is not None:
        for x, y in tetris.current.cells:
            board[int(y)][int(x)] = 2
    return {
        "width": tetris.width,
        "height": tetris.height,
        "score": tetris.score,
        "level": tetris.level,
        "lines": tetris.lines_cleared,
        "game_over": tetris.game_over,
        "board": board,
    }


def apply_action(tetris: Tetris, action: str) -> None:
    """Apply one action to the core; unknown actions are a no-op."""

    handler = _ACTIONS.get(action)
    if handler is not None:
        handler(tetris)
