// Browser Tetris game logic — starter scaffold.
// The mechanical helpers below are done. Complete each method that throws
// "not built yet" so test_game.mjs passes. Coordinates: board[y][x], y=0 top,
// y grows downward. Piece cells are absolute [x, y] pairs. Lines <= 100 chars.

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
    this._seed = seed >>> 0;
  }

  _rand() {
    this._seed = (1664525 * this._seed + 1013904223) >>> 0;
    return this._seed / 0x100000000;
  }

  _choice(keys) {
    return keys[Math.floor(this._rand() * keys.length)];
  }

  _shape(kind) {
    const cells = SHAPES[kind];
    const minY = Math.min(...cells.map(([, y]) => y));
    const offset = Math.floor((this.width - cells.length) / 2);
    return cells.map(([x, y]) => [x + offset, y - minY]);
  }

  _fits(cells) {
    return cells.every(
      ([x, y]) => x >= 0 && x < this.width && y >= 0 && y < this.height && this.board[y][x] === 0,
    );
  }

  _lock() {
    for (const [x, y] of this.current.cells) {
      this.board[y][x] = 1;
    }
  }

  _fullRows() {
    const rows = [];
    for (let y = 0; y < this.height; y += 1) {
      if (this.board[y].every((cell) => cell !== 0)) rows.push(y);
    }
    return rows;
  }

  spawn(kind) {
    throw new Error("not built yet: use _shape; set current or gameOver via _fits");
  }

  move(dx, dy) {
    throw new Error("not built yet: shift current cells by (dx,dy) if _fits; return moved?");
  }

  rotate() {
    throw new Error("not built yet: rotate about centre cell; O returns true; apply if _fits");
  }

  clearLines() {
    throw new Error("not built yet: drop _fullRows, pad top, update lines/level/score, return n");
  }

  hardDrop() {
    throw new Error("not built yet: move(0,1) until blocked, _lock, clearLines, spawn next");
  }

  tick() {
    throw new Error("not built yet: move(0,1) else _lock + clearLines + spawn");
  }
}

export function gameState(game) {
  throw new Error("not built yet: copy board, mark active cells 2 (locked stay 1), no mutation");
}

export function applyAction(game, action) {
  throw new Error("not built yet: left/right/down/rotate/drop -> methods; else no-op");
}

export const CONSTANTS = { WIDTH, HEIGHT, Piece };
