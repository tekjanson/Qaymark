// Browser wiring for the playable Tetris. Uses the gated logic in game.js and
// draws the board on a canvas, mapping keyboard and buttons to game actions.
import { Tetris, gameState, applyAction, SHAPES } from "./game.js";

const CELL = 32;
const COLORS = { 0: "#111827", 1: "#8b5cf6", 2: "#f59e0b" };
const KEYS = { ArrowLeft: "left", ArrowRight: "right", ArrowDown: "down", ArrowUp: "rotate" };

const canvas = document.getElementById("board");
const ctx = canvas.getContext("2d");
const scoreEl = document.getElementById("score");
const levelEl = document.getElementById("level");
const linesEl = document.getElementById("lines");
const messageEl = document.getElementById("message");

const kinds = Object.keys(SHAPES);
let game = new Tetris();
let running = false;
let paused = false;
let last = 0;

function randomKind() {
  return kinds[Math.floor(Math.random() * kinds.length)];
}

function render() {
  const state = gameState(game);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (let y = 0; y < state.height; y += 1) {
    for (let x = 0; x < state.width; x += 1) {
      ctx.fillStyle = COLORS[state.board[y][x]] ?? "#334155";
      ctx.fillRect(x * CELL, y * CELL, CELL - 1, CELL - 1);
    }
  }
  scoreEl.textContent = String(state.score);
  levelEl.textContent = String(state.level);
  linesEl.textContent = String(state.lines);
  if (state.gameOver) {
    messageEl.textContent = "Game over. Press Restart.";
  } else {
    messageEl.textContent = paused ? "Paused" : "";
  }
}

function step(now) {
  if (!running) return;
  const delay = Math.max(120, 650 - (game.level - 1) * 50);
  if (!paused && now - last > delay) {
    game.tick();
    if (game.current === null || game.gameOver) {
      game.spawn(randomKind());
    }
    last = now;
  }
  render();
  requestAnimationFrame(step);
}

function start() {
  if (game.gameOver) {
    game = new Tetris();
  }
  if (game.current === null) {
    game.spawn(randomKind());
  }
  running = true;
  paused = false;
  last = performance.now();
  render();
  requestAnimationFrame(step);
}

function togglePause() {
  if (!running) return;
  paused = !paused;
  render();
}

function restart() {
  game = new Tetris();
  game.spawn(randomKind());
  running = true;
  paused = false;
  last = performance.now();
  render();
  requestAnimationFrame(step);
}

const BUTTONS = { "start": start, "pause": togglePause, "restart": restart };

function onKeydown(event) {
  if (event.code === "KeyP") {
    togglePause();
    return;
  }
  if (event.code === "KeyR") {
    restart();
    return;
  }
  if (!running || paused || game.gameOver) return;
  if (event.code === "Space") {
    applyAction(game, "drop");
    game.spawn(randomKind());
  } else if (KEYS[event.code]) {
    applyAction(game, KEYS[event.code]);
  }
  render();
}

for (const button of document.querySelectorAll("button[data-action]")) {
  button.addEventListener("click", () => {
    const handler = BUTTONS[button.dataset.action];
    if (handler) handler();
  });
}
document.addEventListener("keydown", onKeydown);
render();
