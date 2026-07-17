"""Python seam for the playable web Tetris job.

The harness should fill these functions in so `test_webtetris.py` passes.
"""

from __future__ import annotations

from tetris import Tetris


def game_state(tetris: Tetris) -> dict:
    raise NotImplementedError("Return a JSON-friendly snapshot of the game.")


def apply_action(tetris: Tetris, action: str) -> None:
    raise NotImplementedError("Apply one action to the current Tetris state.")
