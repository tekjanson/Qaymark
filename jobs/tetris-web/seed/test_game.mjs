// Fixed acceptance tests for the browser Tetris game logic (game.js).
// The harness must make game.js pass these; it may not edit this file.
// Run with: node --test test_game.mjs

import { test } from "node:test";
import assert from "node:assert/strict";

import { Tetris, gameState, applyAction } from "./game.js";

test("state reports all fields", () => {
  const t = new Tetris();
  t.spawn("O");
  const s = gameState(t);
  assert.equal(s.width, 10);
  assert.equal(s.height, 20);
  assert.equal(s.score, 0);
  assert.equal(s.level, 1);
  assert.equal(s.lines, 0);
  assert.equal(s.gameOver, false);
  assert.equal(s.board.length, 20);
  assert.ok(s.board.every((row) => row.length === 10));
});

test("active piece marked two", () => {
  const t = new Tetris();
  t.spawn("O");
  const s = gameState(t);
  let twos = 0;
  for (const row of s.board) {
    for (const c of row) {
      if (c === 2) twos += 1;
    }
  }
  assert.equal(twos, 4);
});

test("locked cells marked one and board not mutated", () => {
  const t = new Tetris();
  t.board[19][0] = 1;
  t.spawn("O");
  const s = gameState(t);
  assert.equal(s.board[19][0], 1);
  const values = new Set();
  for (const row of t.board) {
    for (const c of row) values.add(c);
  }
  assert.ok([...values].every((v) => v === 0 || v === 1));
});

test("left then right restores position", () => {
  const t = new Tetris();
  t.spawn("O");
  const before = t.current.cells.map(([x, y]) => [x, y]);
  applyAction(t, "left");
  applyAction(t, "right");
  assert.deepEqual(t.current.cells, before);
});

test("down moves the piece down by one", () => {
  const t = new Tetris();
  t.spawn("O");
  const before = t.current.cells.map(([x, y]) => [x, y + 1]);
  applyAction(t, "down");
  assert.deepEqual(t.current.cells, before);
});

test("drop locks four cells and respawns", () => {
  const t = new Tetris();
  t.spawn("O");
  applyAction(t, "drop");
  let filled = 0;
  for (const row of t.board) {
    for (const c of row) {
      if (c !== 0) filled += 1;
    }
  }
  assert.equal(filled, 4);
  assert.ok(t.current !== null);
});

test("full row clears and scores", () => {
  const t = new Tetris();
  for (let x = 0; x < 10; x += 1) t.board[19][x] = 1;
  const cleared = t.clearLines();
  assert.equal(cleared, 1);
  assert.equal(t.score, 100);
  assert.ok(t.board[19].every((c) => c === 0));
});

test("unknown action is a no-op", () => {
  const t = new Tetris();
  t.spawn("O");
  const before = t.current.cells.map(([x, y]) => [x, y]);
  applyAction(t, "nope");
  assert.deepEqual(t.current.cells, before);
});
