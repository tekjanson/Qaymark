"""Aggressive health checks and self-healing recovery for the factory.

The overnight failure mode was: a CPU-only box running several loops at once
thrashed Ollama until inference wedged, and a hung generation held the shared
turn lock so every loop froze for hours with no watchdog. This module gives the
keeper eyes and hands:

- ``ollama_healthy`` — a fast, hard-bounded probe that the model actually
  answers (not just that the port is open).
- ``recent_progress`` — a heartbeat: has any loop advanced lately?
- ``recover`` — reboot into a clean working mode: kill wedged supervisors, clear
  the stale turn lock and generation markers, optionally restart the runtime.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import ARTIFACT_DIR_NAME

TURN_LOCK = ".turn.lock"


@dataclass
class HealthReport:
    ollama_ok: bool
    progressing: bool
    detail: str

    @property
    def healthy(self) -> bool:
        return self.ollama_ok and self.progressing


def ollama_healthy(base_url: str, model: str, timeout: float = 30.0) -> bool:
    """True only if the model actually returns a token within *timeout*."""

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "reply with only: OK"}],
        "stream": False,
        "options": {"num_predict": 5},
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return False
    return bool(body.get("message", {}).get("content", "").strip())


def _newest_mtime(root: Path) -> float:
    """The most recent generation/attempt activity across all workspaces."""

    newest = 0.0
    for artifact in root.glob(f"*/{ARTIFACT_DIR_NAME}"):
        for name in ("generation.txt", "status.json"):
            path = artifact / name
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
        for attempt in artifact.glob("run-attempt-*.json"):
            try:
                newest = max(newest, attempt.stat().st_mtime)
            except OSError:
                continue
    return newest


def recent_progress(root: Path, window: float = 900.0) -> bool:
    """True if any loop touched an artifact within *window* seconds."""

    newest = _newest_mtime(root)
    if newest == 0.0:
        return True  # nothing has run yet; not a stall
    return (time.time() - newest) < window


def check(root: Path, base_url: str, model: str, window: float = 900.0) -> HealthReport:
    """Assess health without fighting live work.

    Active progress *is* proof that Ollama is up, so when a loop has advanced
    recently we skip the probe entirely — otherwise the probe queues behind the
    running generation on a single-threaded CPU, times out, and falsely reports
    Ollama down. Only when nothing has moved do we probe, and only then can a
    recovery be warranted.
    """

    if recent_progress(root, window):
        return HealthReport(ollama_ok=True, progressing=True, detail="progressing")
    ok = ollama_healthy(base_url, model)
    detail = f"stalled; ollama={'up' if ok else 'DOWN'}"
    return HealthReport(ollama_ok=ok, progressing=False, detail=detail)


def _kill_supervisors(root: Path) -> list[str]:
    """Kill every loop supervisor via its pidfile; clear its pidfile."""

    killed: list[str] = []
    for artifact in root.glob(f"*/{ARTIFACT_DIR_NAME}"):
        pidfile = artifact / "supervisor.pid"
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            continue
        if pid > 0:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except OSError:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
            killed.append(artifact.parent.name)
        try:
            pidfile.unlink()
        except OSError:
            pass
    return killed


def _clear_stale_markers(root: Path) -> None:
    """Remove the shared turn lock and mark hung generations done."""

    holder = root / TURN_LOCK / "holder"
    try:
        holder.unlink()
    except OSError:
        pass
    for state in root.glob(f"*/{ARTIFACT_DIR_NAME}/generation.state"):
        try:
            if state.read_text(encoding="utf-8").strip() == "active":
                state.write_text("done", encoding="utf-8")
        except OSError:
            continue


def _restart_runtime() -> str:
    """Restart the model runtime if a restart command is configured."""

    cmd = os.getenv("QAYMARK_OLLAMA_RESTART_CMD", "")
    if not cmd:
        return "runtime restart skipped (set QAYMARK_OLLAMA_RESTART_CMD to enable)"
    try:
        subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"runtime restart failed: {exc}"
    return "runtime restarted"


def recover(root: Path) -> dict:
    """Reboot the factory into a clean working mode after a wedge."""

    killed = _kill_supervisors(root)
    time.sleep(3)
    _clear_stale_markers(root)
    runtime = _restart_runtime()
    return {"killed": killed, "runtime": runtime}
