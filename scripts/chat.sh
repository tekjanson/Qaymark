#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Load .env so the model and endpoint are configured in one place.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

MODEL="${OLLAMA_MODEL:-qwen2.5-coder:3b}"
BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 \"your prompt\"" >&2
  exit 1
fi

python3 - "$MODEL" "$BASE_URL" "$*" <<'PY'
import json
import sys
import urllib.request

model, base_url, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
payload = {
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "stream": False,
}
request = urllib.request.Request(
    base_url.rstrip("/") + "/api/chat",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=600) as response:
    body = json.loads(response.read().decode("utf-8"))
print(body.get("message", {}).get("content", ""), end="")
PY
