"""Auto source control: save load-bearing work to git the moment it goes green.

The factory's whole point is forward progress that is *kept*. A build that
passes every gate is load-bearing, so it must be committed — otherwise a later
attempt (or a workspace cleanup) can silently throw the work away, which is
exactly the "nothing got pushed through" failure this module prevents.

``checkin_workspace`` is idempotent: it initialises a repo on first use, writes
a ``.gitignore`` that excludes harness churn, then commits only when the
tracked, load-bearing files actually changed. Calling it every keeper cycle for
every green loop is therefore cheap and safe.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import ARTIFACT_DIR_NAME

GITIGNORE_LINES = (ARTIFACT_DIR_NAME + "/", "__pycache__/", "*.pyc", ".turn.lock")
_AUTHOR_NAME = "Qaymark Keeper"
_AUTHOR_EMAIL = "keeper@qaymark.local"


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    """Run one git command in ``workspace`` with a pinned identity."""

    command = [
        "git",
        "-c", f"user.name={_AUTHOR_NAME}",
        "-c", f"user.email={_AUTHOR_EMAIL}",
        *args,
    ]
    return subprocess.run(
        command, cwd=str(workspace), capture_output=True, text=True, check=False
    )


def _is_repo(workspace: Path) -> bool:
    return (workspace / ".git").exists()


def _ensure_repo(workspace: Path) -> None:
    if not _is_repo(workspace):
        _git(workspace, "init", "-q")
    _write_gitignore(workspace)


def _write_gitignore(workspace: Path) -> None:
    path = workspace / ".gitignore"
    body = "\n".join(GITIGNORE_LINES) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == body:
        return
    path.write_text(body, encoding="utf-8")


def _has_staged_changes(workspace: Path) -> bool:
    """True when the index differs from HEAD (something worth committing)."""

    result = _git(workspace, "diff", "--cached", "--quiet")
    return result.returncode != 0


def _head_sha(workspace: Path) -> str | None:
    result = _git(workspace, "rev-parse", "--short", "HEAD")
    sha = result.stdout.strip()
    return sha or None


def checkin_workspace(workspace: Path, message: str) -> dict:
    """Commit a workspace's load-bearing files; a no-op when nothing changed."""

    workspace = Path(workspace)
    if not workspace.is_dir():
        return {"committed": False, "detail": "no workspace", "sha": None}
    _ensure_repo(workspace)
    _git(workspace, "add", "-A")
    if not _has_staged_changes(workspace):
        return {"committed": False, "detail": "already saved", "sha": _head_sha(workspace)}
    result = _git(workspace, "commit", "-q", "-m", message)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:200] or "commit failed"
        return {"committed": False, "detail": detail, "sha": _head_sha(workspace)}
    return {"committed": True, "detail": "checked in", "sha": _head_sha(workspace)}


def checkin_green(workspace: Path, name: str, build: int) -> dict:
    """Check in a green loop with a descriptive, build-stamped message."""

    message = f"{name}: green build {build} (auto check-in)"
    return checkin_workspace(workspace, message)
