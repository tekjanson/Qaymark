"""Robust extraction of a JSON action payload from model output."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _try_load(candidate: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _from_braces(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    return _try_load(text[start : end + 1])


def extract_json_payload(text: str) -> dict[str, Any]:
    """Parse the first JSON object found in *text*.

    Tries the raw string, fenced code blocks, then the outermost brace span.
    Raises ValueError when no JSON object can be recovered.
    """

    stripped = text.strip()
    direct = _try_load(stripped)
    if direct is not None:
        return direct

    for candidate in _FENCE_RE.findall(stripped):
        parsed = _try_load(candidate)
        if parsed is not None:
            return parsed

    braced = _from_braces(stripped)
    if braced is not None:
        return braced

    raise ValueError(f"Could not parse JSON from model response: {text[:300]}")
