#!/usr/bin/env bash
#
# Run the Qaymark factory against the playable web Tetris job.
set -euo pipefail

cd "$(dirname "$0")/../.."

WORKSPACE="${1:-/tmp/qaymark-tetris-web}"
WORKERS="${WORKERS:-1}"
MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
ATTEMPTS="${HARNESS_MAX_ATTEMPTS:-8}"

export HARNESS_REQUEST_TIMEOUT="${HARNESS_REQUEST_TIMEOUT:-1800}"
FMT_BIN="${HOME}/.cache/local-coding-harness/fmt-venv/bin"
if [[ -d "$FMT_BIN" ]]; then
  export PATH="${FMT_BIN}:${PATH}"
fi

VALIDATE="python3 -m unittest test_webtetris"
VALIDATE="${VALIDATE} && node --test test_game.mjs && node --check app.js"

python3 scripts/code_harness.py \
  --task "$(cat jobs/tetris-web/TASK.md)" \
  --seed jobs/tetris-web/seed \
  --starter jobs/tetris-web/starter \
  --workspace "$WORKSPACE" \
  --validation-command "$VALIDATE" \
  --workers "$WORKERS" \
  --max-attempts "$ATTEMPTS" \
  --model "$MODEL"

echo
echo "Winning game (if any) is under: $WORKSPACE (or $WORKSPACE/result for a fleet)"

