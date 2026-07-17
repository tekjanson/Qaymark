const WIDTH = 10;
const HEIGHT = 20;
const CELL = 32;

function gameState() {
  throw new Error("Implement the browser state snapshot.");
}

function applyAction() {
  throw new Error("Implement the browser action handler.");
}

function render() {
  throw new Error("Implement board rendering.");
}

function startGame() {
  throw new Error("Implement start / restart behavior.");
}

function togglePause() {
  throw new Error("Implement pause and resume.");
}

function restartGame() {
  throw new Error("Implement restart.");
}

function onKeydown() {
  throw new Error("Wire keyboard controls to the game actions.");
}

document.getElementById("start").addEventListener("click", startGame);
document.getElementById("pause").addEventListener("click", togglePause);
document.getElementById("restart").addEventListener("click", restartGame);
document.addEventListener("keydown", onKeydown);
