#!/usr/bin/env bash
#
# Run the Qaymark fleet against the Tetris job: several workers race to make
# tetris.py pass the fixed acceptance tests AND the strict hygiene gate.
set -euo pipefail

cd "$(dirname "$0")/../.."

WORKSPACE="${1:-/tmp/qaymark-tetris}"
WORKERS="${WORKERS:-1}"
MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
ATTEMPTS="${HARNESS_MAX_ATTEMPTS:-8}"

# Give the harness a long request timeout (local models are slow on CPU) and
# put any black install on PATH so generated code is auto-formatted before the
# hygiene gate.
export HARNESS_REQUEST_TIMEOUT="${HARNESS_REQUEST_TIMEOUT:-1800}"
FMT_BIN="${HOME}/.cache/local-coding-harness/fmt-venv/bin"
if [[ -d "$FMT_BIN" ]]; then
  export PATH="${FMT_BIN}:${PATH}"
fi

python3 scripts/code_harness.py \
  --task "$(cat jobs/tetris/TASK.md)" \
  --seed jobs/tetris/seed \
  --starter jobs/tetris/starter \
  --workspace "$WORKSPACE" \
  --validation-command "python3 -m unittest test_tetris" \
  --workers "$WORKERS" \
  --max-attempts "$ATTEMPTS" \
  --model "$MODEL"

echo
echo "Winning game (if any) is under: $WORKSPACE (or $WORKSPACE/result for a fleet)"
