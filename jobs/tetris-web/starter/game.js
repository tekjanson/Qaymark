// Browser Tetris game logic — starter scaffold.
// The harness completes each method body so test_game.mjs passes.
// Coordinates: board[y][x], y=0 is the top row, y grows downward. Piece cells
// are absolute [x, y] pairs. Keep every line <= 100 chars.

const WIDTH = 10;
const HEIGHT = 20;
export const SHAPES = {
  I: [[0, 1], [1, 1], [2, 1], [3, 1]],
  O: [[0, 0], [1, 0], [0, 1], [1, 1]],
  T: [[1, 0], [0, 1], [1, 1], [2, 1]],
  S: [[1, 0], [2, 0], [0, 1], [1, 1]],
  Z: [[0, 0], [1, 0], [1, 1], [2, 1]],
  J: [[0, 0], [0, 1], [1, 1], [2, 1]],
  L: [[2, 0], [0, 1], [1, 1], [2, 1]],
};
export const SCORE_TABLE = { 1: 100, 2: 300, 3: 500, 4: 800 };

class Piece {
  constructor(kind, cells) {
    this.kind = kind;
    this.cells = cells;
  }
}

export class Tetris {
  constructor(width = WIDTH, height = HEIGHT, seed = 0) {
    this.width = width;
    this.height = height;
    this.board = Array.from({ length: height }, () => Array(width).fill(0));
    this.score = 0;
    this.linesCleared = 0;
    this.level = 1;
    this.gameOver = false;
    this.current = null;
    this._seed = seed;
  }

  _shape(kind) {
    throw new Error("not built yet: return spawn cells for kind, min y == 0");
  }

  _fits(cells) {
    throw new Error("not built yet: every cell in bounds and board empty");
  }

  spawn(kind) {
    throw new Error("not built yet: place a piece, set gameOver if it cannot fit");
  }

  move(dx, dy) {
    throw new Error("not built yet: shift current if it fits, return moved?");
  }

  rotate() {
    throw new Error("not built yet: rotate clockwise; O is a no-op");
  }

  clearLines() {
    throw new Error("not built yet: clear full rows, update score/level/lines");
  }

  hardDrop() {
    throw new Error("not built yet: fall, lock, clearLines, spawn next");
  }

  tick() {
    throw new Error("not built yet: one gravity step or lock+clear+spawn");
  }
}

export function gameState(game) {
  throw new Error("not built yet: snapshot with active=2, locked=1, no mutation");
}

export function applyAction(game, action) {
  throw new Error("not built yet: map left/right/down/rotate/drop to methods");
}

export const CONSTANTS = { WIDTH, HEIGHT, Piece };
