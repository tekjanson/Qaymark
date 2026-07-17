#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Load .env if present so ports/model/auth are configured in one place.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

MODEL="${OLLAMA_MODEL:-qwen2.5-coder:3b}"
WEBUI_DATA_DIR="${WEBUI_DATA_DIR:-./open-webui}"
WEBUI_PORT="${WEBUI_PORT:-8090}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
# Non-destructive by default. Set RESET_WEBUI_DATA=1 to wipe the WebUI DB
# (only needed the first time you disable WEBUI_AUTH on a store with users).
RESET_WEBUI_DATA="${RESET_WEBUI_DATA:-0}"

if [[ "$RESET_WEBUI_DATA" == "1" ]]; then
  echo "⚠️  RESET_WEBUI_DATA=1 — wiping local Open WebUI database and vector store..."
  rm -f "$WEBUI_DATA_DIR/webui.db" "$WEBUI_DATA_DIR/chroma.sqlite3"
  rm -rf "$WEBUI_DATA_DIR/vector_db"
fi

docker compose down --remove-orphans >/dev/null 2>&1 || true

echo "Starting Ollama and Open WebUI..."
docker compose up -d --force-recreate

echo "Waiting for Ollama to become ready..."
for _ in $(seq 1 60); do
  if docker compose exec -T ollama ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Pulling model: $MODEL"
docker compose exec -T ollama ollama pull "$MODEL"

echo
echo "✅ Local coding assistant is ready."
echo "- Open WebUI: http://localhost:${WEBUI_PORT}"
echo "- Ollama API: http://localhost:${OLLAMA_PORT}"
echo "- Default model: $MODEL"
echo
echo "Run the guardrailed harness with:"
echo "  make harness TASK=\"...\" WORKSPACE=<dir>"
