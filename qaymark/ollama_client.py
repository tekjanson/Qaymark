"""Minimal Ollama chat client (stdlib only)."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Callable


def _timeout() -> int:
    return int(os.getenv("HARNESS_REQUEST_TIMEOUT", "600"))


def _deadline() -> float:
    """Hard wall-clock cap on a single generation, so a dribbling or wedged
    Ollama can never freeze a loop for hours (the streaming socket timeout
    resets on every keepalive byte, so it is not enough on its own)."""

    return float(os.getenv("HARNESS_GEN_DEADLINE", "300"))


def _read_stream(response, on_delta: Callable[[str], None] | None) -> str:
    """Accumulate a streamed /api/chat response, emitting each content chunk."""

    parts: list[str] = []
    start = time.monotonic()
    deadline = _deadline()
    for raw in response:
        if time.monotonic() - start > deadline:
            break
        line = raw.decode("utf-8").strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        chunk = event.get("message", {}).get("content", "")
        if chunk:
            parts.append(chunk)
            if on_delta is not None:
                on_delta(chunk)
        if event.get("done"):
            break
    return "".join(parts)


def chat(
    system: str,
    user: str,
    model: str,
    base_url: str,
    on_delta: Callable[[str], None] | None = None,
) -> str:
    """Send a one-shot system+user chat request and return the reply text.

    The response is streamed so callers can watch progress in real time via
    ``on_delta`` (called with each content chunk); the full text is still
    accumulated and returned, preserving the one-shot contract.
    """

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": True,
        "options": {"temperature": 0.2, "num_ctx": 8192},
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_timeout()) as response:
        return _read_stream(response, on_delta)
