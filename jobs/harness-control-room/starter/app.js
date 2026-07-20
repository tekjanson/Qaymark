const state = {
  chat: [{ role: "system", text: "Harness online." }],
  projects: [],
  queue: [],
  paused: false,
};

function renderChat() {
  const list = document.getElementById("chat-log");
  list.innerHTML = state.chat
    .map((item) => `<li><strong>${item.role}:</strong> ${item.text}</li>`)
    .join("");
}

function renderProjects() {
  const list = document.getElementById("project-list");
  list.innerHTML = state.projects
    .map((item) => `<li>${item.title} <span>(${item.status})</span></li>`)
    .join("");
}

function renderQueue() {
  const list = document.getElementById("queue-list");
  const queued = state.queue.length
    ? state.queue
    : state.projects.filter((item) => item.status === "queued");
  const running = state.projects.filter((item) => item.status === "running");
  list.innerHTML = queued
    .concat(running)
    .map((item) => `<li>${item.title} <span>(${item.status})</span></li>`)
    .join("");
  document.getElementById("status-panel").textContent = state.paused
    ? `Queue paused (${queued.length} waiting)`
    : `Queue running (${queued.length} waiting)`;
}

function sendMessage(text) {
  state.chat.push({ role: "operator", text });
  renderChat();
}

function toggleQueue(paused) {
  state.paused = paused;
  renderQueue();
}

function renderAll() {
  renderChat();
  renderProjects();
  renderQueue();
}

document.getElementById("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  if (input.value.trim()) sendMessage(input.value.trim());
  input.value = "";
});

document.getElementById("send-message").addEventListener("click", (event) => {
  event.preventDefault();
});

renderAll();

document.getElementById("pause-queue").addEventListener("click", () => {
  toggleQueue(true);
});

document.getElementById("resume-queue").addEventListener("click", () => {
  toggleQueue(false);
});
