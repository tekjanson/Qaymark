#!/usr/bin/env bash
#
# Run the Qaymark factory against the harness control room job.
set -euo pipefail

cd "$(dirname "$0")/../.."

DEFAULT_WORKSPACE="${XDG_STATE_HOME:-$HOME/.local/state}/qaymark/control-room"
WORKSPACE="${1:-$DEFAULT_WORKSPACE}"
WORKERS="${WORKERS:-1}"
MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
ATTEMPTS="${HARNESS_MAX_ATTEMPTS:-8}"

export HARNESS_REQUEST_TIMEOUT="${HARNESS_REQUEST_TIMEOUT:-1800}"
FMT_BIN="${HOME}/.cache/local-coding-harness/fmt-venv/bin"
if [[ -d "$FMT_BIN" ]]; then
  export PATH="${FMT_BIN}:${PATH}"
fi

mkdir -p "$WORKSPACE"

VALIDATE="python3 -m unittest test_control_room && node --check app.js"

python3 scripts/code_harness.py \
  --task "$(cat jobs/harness-control-room/TASK.md)" \
  --seed jobs/harness-control-room/seed \
  --starter jobs/harness-control-room/starter \
  --workspace "$WORKSPACE" \
  --validation-command "$VALIDATE" \
  --workers "$WORKERS" \
  --max-attempts "$ATTEMPTS" \
  --model "$MODEL"

echo
echo "Winning workspace (if any) is under: $WORKSPACE (or $WORKSPACE/result for a fleet)"
