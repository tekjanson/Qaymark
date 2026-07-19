"""Around-the-clock supervisor: keep a workspace converging under operator control.

``run_harness`` converges once and exits. The supervisor keeps the factory alive
and *controllable*: after the first build it watches two channels every poll —

- the **feedback** channel (a human note that triggers a rebuild), and
- the **control** channel (pause, resume, redirect, or stop the loop).

Feedback-driven and redirect-driven reruns are snapshotted first and rolled back
if they fail to pass, so the workspace never regresses to a broken state. The
supervisor registers its PID so a dashboard can see which loops are alive and
steer them without touching the terminal or Copilot.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from . import chat, control
from .config import HarnessConfig
from .loop import _feedback_path, _write_status, run_harness
from .workspace import iter_files


@dataclass
class SupervisorResult:
    cycles: int
    passed: bool
    last_exit: int


def _feedback_signature(config: HarnessConfig) -> str:
    """A cheap fingerprint of the feedback channel (empty when absent)."""

    path = _feedback_path(config)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _snapshot_files(workspace: Path) -> dict[str, bytes]:
    """Capture the current generated files (ignored dirs are skipped)."""

    snapshot: dict[str, bytes] = {}
    for path in iter_files(workspace):
        snapshot[path.relative_to(workspace).as_posix()] = path.read_bytes()
    return snapshot


def _restore_files(workspace: Path, snapshot: dict[str, bytes]) -> None:
    """Restore a snapshot, deleting any files created since it was taken."""

    current = {path.relative_to(workspace).as_posix() for path in iter_files(workspace)}
    for rel in current - set(snapshot):
        (workspace / rel).unlink(missing_ok=True)
    for rel, data in snapshot.items():
        target = workspace / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _rerun_with_rollback(config: HarnessConfig) -> int:
    """Re-run the harness; roll back the workspace if it fails to pass."""

    snapshot = _snapshot_files(config.workspace)
    exit_code = run_harness(config)
    if exit_code != 0:
        _restore_files(config.workspace, snapshot)
        _write_status(config, "reverted")
        print("supervisor: rerun failed the gate, reverted to last good build", flush=True)
    return exit_code


def _maybe_rebuild(
    config: HarnessConfig, command: control.LoopControl, consumed: str
) -> tuple[int, str] | None:
    """Rebuild on a redirect or on new feedback; return (exit, consumed) or None."""

    if command.redirect_task:
        config.task = command.redirect_task
        control.clear_redirect(config.workspace)
        chat.post(config.workspace, "system", "Redirected to a new task; rebuilding now.")
        print("supervisor: redirected to a new task, rebuilding", flush=True)
        return _rerun_with_rollback(config), _feedback_signature(config)
    current = _feedback_signature(config)
    if current and current != consumed:
        chat.post(config.workspace, "system", "New feedback received; rebuilding now.")
        print("supervisor: new feedback received, rebuilding", flush=True)
        return _rerun_with_rollback(config), current
    return None


def _retry_until_green(config: HarnessConfig) -> tuple[int, str] | None:
    """A loop that is not green keeps trying — but only on its turn.

    Only one loop generates at a time (the factory turn), so loops share the
    machine fairly instead of all hammering it at once. A loop that cannot take
    the turn waits and tries again on the next poll.
    """

    if not control.acquire_turn(config.workspace):
        _write_status(config, "waiting")
        chat.post_unique(config.workspace, "system", "Waiting for my turn on the factory floor.")
        return None
    try:
        print("supervisor: not green yet, taking a turn to keep trying", flush=True)
        exit_code = _rerun_with_rollback(config)
    finally:
        control.release_turn(config.workspace)
    return exit_code, _feedback_signature(config)


def _initial_build(
    config: HarnessConfig, poll_interval: float, max_cycles: int | None
) -> int:
    """Run the first build. In forever mode this waits for the factory turn so
    loops start one at a time; bounded/one-shot runs build immediately."""

    if max_cycles is not None:
        return run_harness(config)
    while True:
        command = control.read_control(config.workspace)
        if command.stop:
            _write_status(config, "stopped")
            return 1
        if command.paused:
            _write_status(config, "paused")
            time.sleep(poll_interval)
            continue
        if control.acquire_turn(config.workspace):
            try:
                return run_harness(config)
            finally:
                control.release_turn(config.workspace)
        _write_status(config, "waiting")
        time.sleep(poll_interval)


def _run_supervisor(
    config: HarnessConfig, poll_interval: float, max_cycles: int | None
) -> SupervisorResult:
    exit_code = _initial_build(config, poll_interval, max_cycles)
    passed = exit_code == 0
    consumed = _feedback_signature(config)
    cycles = 0

    while max_cycles is None or cycles < max_cycles:
        command = control.read_control(config.workspace)
        if command.stop:
            _write_status(config, "stopped")
            chat.post(config.workspace, "system", "Stopped by operator.")
            print("supervisor: stop requested, exiting the loop", flush=True)
            break
        if command.paused:
            _write_status(config, "paused")
            chat.post_unique(config.workspace, "system", "Paused by operator.")
            if max_cycles is not None:
                break
            time.sleep(poll_interval)
            continue
        outcome = _maybe_rebuild(config, command, consumed)
        if outcome is None and not passed:
            outcome = _retry_until_green(config)
        if outcome is not None:
            exit_code, consumed = outcome
            passed = exit_code == 0
            cycles += 1
        if max_cycles is not None:
            break
        if passed:
            _write_status(config, "watching")
        time.sleep(poll_interval)

    control.release_turn(config.workspace)
    return SupervisorResult(cycles=cycles, passed=passed, last_exit=exit_code)


def supervise(
    config: HarnessConfig,
    poll_interval: float = 5.0,
    max_cycles: int | None = None,
) -> SupervisorResult:
    """Build once, then rebuild on feedback or redirect until stopped.

    Set ``max_cycles`` to bound the number of driven rebuilds (used by tests and
    for one-shot runs); leave it ``None`` to run around the clock. The loop is
    controllable the whole time through the workspace's control channel.
    """

    control.write_pidfile(config.workspace)
    try:
        return _run_supervisor(config, poll_interval, max_cycles)
    finally:
        control.clear_pidfile(config.workspace)
