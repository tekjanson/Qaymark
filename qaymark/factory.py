"""Around-the-clock supervisor: keep a workspace converging on human feedback.

`run_harness` converges once and exits. The supervisor keeps the factory alive:
after the first build it watches the workspace's feedback channel and, when a
human leaves new feedback in the dashboard, it re-runs the guardrailed loop so
the code rewrites itself. Feedback-driven reruns are snapshotted first and rolled
back if they fail to pass, so the workspace never regresses to a broken state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

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


def supervise(
    config: HarnessConfig,
    poll_interval: float = 5.0,
    max_cycles: int | None = None,
) -> SupervisorResult:
    """Build once, then rebuild whenever new human feedback arrives.

    Set ``max_cycles`` to bound the number of feedback-driven rebuilds (used by
    tests and for one-shot runs); leave it ``None`` to run around the clock.
    """

    exit_code = run_harness(config)
    passed = exit_code == 0
    consumed = _feedback_signature(config)
    cycles = 0

    while max_cycles is None or cycles < max_cycles:
        _write_status(config, "watching")
        current = _feedback_signature(config)
        if current and current != consumed:
            print("supervisor: new feedback received, rebuilding", flush=True)
            exit_code = _rerun_with_rollback(config)
            passed = exit_code == 0
            consumed = current
            cycles += 1
            continue
        if max_cycles is not None:
            break
        time.sleep(poll_interval)

    return SupervisorResult(cycles=cycles, passed=passed, last_exit=exit_code)
