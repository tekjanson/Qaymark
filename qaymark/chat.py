"""Two-way chat channel between the operator and a working loop.

Feedback is a blunt one-way note; chat is a conversation. The loop posts what
it is doing (starting a build, which gate failed, that it went green, that it is
waiting for its turn) so a human can *understand* the working thread, and the
human posts back to steer it. Operator messages become feedback that drives the
next rebuild, or a redirect when prefixed with ``/redirect``.

The transcript is a JSON-lines file under the workspace's ``.harness`` dir so it
survives restarts and needs no database.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .config import ARTIFACT_DIR_NAME

CHAT_FILE = "chat.jsonl"
ROLES = ("operator", "loop", "system")
_MAX_TEXT = 4000


@dataclass
class ChatMessage:
    role: str
    text: str
    ts: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "text": self.text, "ts": self.ts}


def chat_path(workspace: Path) -> Path:
    return workspace / ARTIFACT_DIR_NAME / CHAT_FILE


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def post(workspace: Path, role: str, text: str) -> ChatMessage | None:
    """Append one message to the transcript; ignore empty or unknown roles."""

    clean = text.strip()[:_MAX_TEXT]
    if role not in ROLES or not clean:
        return None
    message = ChatMessage(role=role, text=clean, ts=_stamp())
    path = chat_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(message.to_dict()) + "\n")
    return message


def post_unique(workspace: Path, role: str, text: str) -> ChatMessage | None:
    """Post only when it differs from the last message (avoids poll spam)."""

    existing = read(workspace, limit=1)
    clean = text.strip()[:_MAX_TEXT]
    if existing and existing[-1]["role"] == role and existing[-1]["text"] == clean:
        return None
    return post(workspace, role, text)


def read(workspace: Path, limit: int = 200) -> list[dict[str, str]]:
    """Return the last *limit* messages as plain dicts (oldest first)."""

    path = chat_path(workspace)
    if not path.exists():
        return []
    messages: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(line)
        if parsed is not None:
            messages.append(parsed)
    return messages[-limit:]


def _parse_line(line: str) -> dict[str, str] | None:
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "role" not in data or "text" not in data:
        return None
    return {"role": str(data["role"]), "text": str(data["text"]), "ts": str(data.get("ts", ""))}
