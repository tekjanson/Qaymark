"""Minimal Ollama chat client (stdlib only)."""

from __future__ import annotations

import json
import urllib.request


def chat(system: str, user: str, model: str, base_url: str, timeout: int = 600) -> str:
    """Send a one-shot system+user chat request and return the reply text."""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body.get("message", {}).get("content", "")
