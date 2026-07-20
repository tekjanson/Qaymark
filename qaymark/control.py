"""Control channel for a supervised loop.

A supervised loop is steered through a small JSON file in the workspace's
``.harness`` directory. The dashboard — or any local tool — writes commands and
the supervisor reads them on every poll. This is the seam that lets a human
pause, resume, redirect, or stop a local loop without touching the code, the
terminal, or Copilot.

The control model is deliberately small and file-based so it survives restarts,
needs no daemon, and can be driven from a browser, a script, or by hand:

- ``paused``        the loop idles instead of rebuilding.
- ``stop``          the loop exits cleanly after the current cycle.
- ``redirect_task`` the loop switches to a new task on the next cycle.
- ``note``          a human-readable reason shown in the UI.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import ARTIFACT_DIR_NAME

CONTROL_FILE = "control.json"
PIDFILE = "supervisor.pid"


@dataclass
class LoopControl:
    """The desired state of a supervised loop, as set by the operator."""

    paused: bool = False
    stop: bool = False
    redirect_task: str | None = None
    note: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _artifact_dir(workspace: Path) -> Path:
    return workspace / ARTIFACT_DIR_NAME


def control_path(workspace: Path) -> Path:
    return _artifact_dir(workspace) / CONTROL_FILE


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def read_control(workspace: Path) -> LoopControl:
    """Read the control channel; an absent or broken file means default state."""

    path = control_path(workspace)
    if not path.exists():
        return LoopControl()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LoopControl()
    if not isinstance(data, dict):
        return LoopControl()
    return LoopControl(
        paused=bool(data.get("paused", False)),
        stop=bool(data.get("stop", False)),
        redirect_task=(str(data["redirect_task"]) if data.get("redirect_task") else None),
        note=str(data.get("note", "")),
        updated_at=str(data.get("updated_at", "")),
    )


def write_control(workspace: Path, control: LoopControl) -> None:
    """Persist the control channel, stamping the update time."""

    control.updated_at = _stamp()
    path = control_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(control.to_dict(), indent=2) + "\n", encoding="utf-8")


def pause(workspace: Path, note: str = "") -> LoopControl:
    control = read_control(workspace)
    control.paused = True
    if note:
        control.note = note
    write_control(workspace, control)
    return control


def resume(workspace: Path, note: str = "") -> LoopControl:
    control = read_control(workspace)
    control.paused = False
    if note:
        control.note = note
    write_control(workspace, control)
    return control


def request_stop(workspace: Path, note: str = "") -> LoopControl:
    control = read_control(workspace)
    control.stop = True
    if note:
        control.note = note
    write_control(workspace, control)
    return control


def redirect(workspace: Path, task: str, note: str = "") -> LoopControl:
    """Point the loop at a new task; it switches on the next cycle."""

    control = read_control(workspace)
    control.redirect_task = task.strip() or None
    control.paused = False
    if note:
        control.note = note
    write_control(workspace, control)
    return control


def clear_redirect(workspace: Path) -> LoopControl:
    control = read_control(workspace)
    control.redirect_task = None
    write_control(workspace, control)
    return control


def pidfile_path(workspace: Path) -> Path:
    return _artifact_dir(workspace) / PIDFILE


def write_pidfile(workspace: Path, pid: int | None = None) -> None:
    path = pidfile_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid if pid is not None else os.getpid()), encoding="utf-8")


def read_pidfile(workspace: Path) -> int | None:
    path = pidfile_path(workspace)
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0") or None
    except (OSError, ValueError):
        return None


def clear_pidfile(workspace: Path) -> None:
    pidfile_path(workspace).unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _pid_is_zombie(pid)


def _pid_is_zombie(pid: int) -> bool:
    """A reaped-but-not-collected child is effectively dead, not running."""

    stat = Path(f"/proc/{pid}/stat")
    try:
        fields = stat.read_text(encoding="utf-8").rsplit(")", 1)
    except (OSError, ValueError):
        return False
    return len(fields) == 2 and fields[1].strip().startswith("Z")


def loop_is_alive(workspace: Path) -> bool:
    """True when a supervisor process is registered and still running."""

    pid = read_pidfile(workspace)
    return pid is not None and _pid_alive(pid)


# --- Turn taking -----------------------------------------------------------
#
# Loops share the factory floor, so they take turns: only one loop actively
# generates at a time. The turn is a single lock directory under the factory
# root (the workspace's parent) whose holder file names the current loop. A
# loop must hold the turn to run an autonomous "keep trying" round, then yields
# it so another loop that is not yet green can take its turn.

TURN_LOCK = ".turn.lock"


def _turn_dir(workspace: Path) -> Path:
    return workspace.parent / TURN_LOCK


def _holder_file(workspace: Path) -> Path:
    return _turn_dir(workspace) / "holder"


def _read_holder(workspace: Path) -> tuple[str, int] | None:
    try:
        raw = _holder_file(workspace).read_text(encoding="utf-8").strip()
        name, pid = raw.rsplit(":", 1)
        return name, int(pid)
    except (OSError, ValueError):
        return None


def _claim_turn(workspace: Path) -> None:
    _holder_file(workspace).write_text(f"{workspace.name}:{os.getpid()}", encoding="utf-8")


def acquire_turn(workspace: Path) -> bool:
    """Try to take the factory turn; True if this loop now holds it."""

    lock = _turn_dir(workspace)
    try:
        lock.mkdir(parents=True)
        _claim_turn(workspace)
        return True
    except FileExistsError:
        holder = _read_holder(workspace)
        if holder is None:
            _claim_turn(workspace)
            return True
        name, pid = holder
        if name == workspace.name:
            return True
        if not _pid_alive(pid):  # holder died without releasing — reclaim it
            _claim_turn(workspace)
            return True
        return False


def release_turn(workspace: Path) -> None:
    holder = _read_holder(workspace)
    if holder is not None and holder[0] != workspace.name:
        return
    _holder_file(workspace).unlink(missing_ok=True)
    try:
        _turn_dir(workspace).rmdir()
    except OSError:
        pass


def current_turn(workspace: Path) -> str | None:
    holder = _read_holder(workspace)
    return holder[0] if holder else None
