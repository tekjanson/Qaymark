#!/usr/bin/env bash
#
# Run the Qaymark fleet against the Tetris job: several workers race to make
# tetris.py pass the fixed acceptance tests AND the strict hygiene gate.
set -euo pipefail

cd "$(dirname "$0")/../.."

WORKSPACE="${1:-/tmp/qaymark-tetris}"
WORKERS="${WORKERS:-3}"
MODEL="${OLLAMA_MODEL:-qwen2.5-coder:7b}"
ATTEMPTS="${HARNESS_MAX_ATTEMPTS:-6}"

python3 scripts/code_harness.py \
  --task "$(cat jobs/tetris/TASK.md)" \
  --seed jobs/tetris/seed \
  --workspace "$WORKSPACE" \
  --validation-command "python3 -m unittest test_tetris" \
  --workers "$WORKERS" \
  --max-attempts "$ATTEMPTS" \
  --model "$MODEL"

echo
echo "Winning game (if any) is under: $WORKSPACE/result"
