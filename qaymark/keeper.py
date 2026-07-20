"""Forever-keeper: keep the factory working, then audit when it goes quiet.

The keeper is a small, resilient loop that watches every job:

- while any job is not green, it makes sure a supervisor is running for it
  (respecting operator pause/stop), so *something is always working*;
- when every job is green (nothing left to build), it writes a one-time audit
  of what was done and posts it to the factory chat as feedback, then keeps
  watching so new work is picked up the moment it appears.

It is pure local process management with a single-instance lock, so a second
``make up`` will not spawn a competing keeper.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from . import chat, checkin, health, orchestrator
from .config import ARTIFACT_DIR_NAME, factory_root

LOCK_NAME = "keeper.lock"
STATE_NAME = "keeper.json"


def _model() -> str:
    return os.getenv("QAYMARK_KEEPER_MODEL", "qwen2.5-coder:3b") or "qwen2.5-coder:3b"


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _max_active() -> int:
    """How many loops may run at once. Default 1: a CPU-only box thrashes and
    wedges Ollama when several loops hammer it, so the clean working mode runs
    one loop at a time."""

    try:
        return max(1, int(os.getenv("QAYMARK_MAX_ACTIVE_LOOPS", "1")))
    except ValueError:
        return 1


def _attempts_per_turn() -> int:
    """How many attempts a job gets before it yields the worker to the next
    pending job. Bounded turns give fair round-robin so one impossible job can
    never hold the only slot forever."""

    try:
        return max(1, int(os.getenv("QAYMARK_ATTEMPTS_PER_TURN", "6")))
    except ValueError:
        return 6


LAUNCHES_NAME = "launches.json"


def _launch_times(root: Path) -> dict:
    path = _root_artifacts(root) / LAUNCHES_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _record_launch(root: Path, name: str) -> None:
    path = _root_artifacts(root) / LAUNCHES_NAME
    data = _launch_times(root)
    data[name] = time.time()
    path.write_text(json.dumps(data), encoding="utf-8")


def rotate_pending(pending: list[str], root: Path) -> list[str]:
    """Order pending jobs least-recently-launched first, so each job takes a
    fair turn at the shared worker instead of one job hogging it forever."""

    times = _launch_times(root)
    return sorted(pending, key=lambda name: times.get(name, 0.0))


@dataclass
class Plan:
    pending: list[str]
    all_green: bool
    audit: str | None


def _root_artifacts(root: Path) -> Path:
    path = root / ARTIFACT_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def pending_jobs(loops: dict[str, dict], job_names: list[str]) -> list[str]:
    """Jobs that need a supervisor: not green, not alive, not paused/stopping."""

    out: list[str] = []
    for name in job_names:
        state = loops.get(name)
        if state is None:
            out.append(name)
            continue
        if state.get("green") or state.get("alive"):
            continue
        if state.get("paused") or state.get("stopping"):
            continue
        out.append(name)
    return out


def audit_report(loops: dict[str, dict], job_names: list[str]) -> str:
    """A concise audit of what each green loop achieved."""

    lines = ["Audit — every job is green. Here is what was done:"]
    for name in job_names:
        state = loops.get(name, {})
        build = state.get("build", 0)
        attempt = state.get("attempt")
        lines.append(f"- {name}: green on build {build} (last attempt {attempt}).")
    lines.append("Nothing left to build. Leave a note or /redirect a loop to start new work.")
    return "\n".join(lines)


def _audit_signature(loops: dict[str, dict], job_names: list[str]) -> str:
    marks = [f"{name}:{loops.get(name, {}).get('build', 0)}" for name in job_names]
    return "|".join(marks)


def make_plan(loops: dict[str, dict], job_names: list[str]) -> Plan:
    pending = pending_jobs(loops, job_names)
    all_green = bool(job_names) and all(
        loops.get(name, {}).get("green") for name in job_names
    )
    audit = audit_report(loops, job_names) if all_green else None
    return Plan(pending=pending, all_green=all_green, audit=audit)


def _loops_by_name(root: Path) -> dict[str, dict]:
    return {state["name"]: state for state in orchestrator.list_loops(root)}


def _keeper_model() -> str | None:
    """The model the keeper launches loops with.

    Defaults to the fast ``qwen2.5-coder:3b`` so loops stay responsive on
    CPU-only hosts (a large model that never emits a token is worse than a
    small one that keeps iterating). Set ``QAYMARK_KEEPER_MODEL`` to override,
    or to an empty string to fall back to each job's own pinned model.
    """

    value = os.getenv("QAYMARK_KEEPER_MODEL", "qwen2.5-coder:3b")
    return value or None


def _already_audited(root: Path, signature: str) -> bool:
    path = _root_artifacts(root) / STATE_NAME
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("audit_signature") == signature


def _remember_audit(root: Path, signature: str) -> None:
    path = _root_artifacts(root) / STATE_NAME
    payload = {"audit_signature": signature, "ts": time.time()}
    path.write_text(json.dumps(payload), encoding="utf-8")


JOURNAL_NAME = "progress.jsonl"


def journal_snapshot(loops: dict[str, dict], job_names: list[str]) -> dict:
    """A compact, auditable snapshot of the factory's progress this cycle."""

    rows = []
    for name in job_names:
        state = loops.get(name, {})
        rows.append({
            "name": name,
            "phase": state.get("phase", "idle"),
            "attempt": state.get("attempt"),
            "build": state.get("build", 0),
            "green": bool(state.get("green")),
            "alive": bool(state.get("alive")),
        })
    green = sum(1 for row in rows if row["green"])
    return {"ts": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "green": green, "total": len(rows), "loops": rows}


def _append_journal(root: Path, snapshot: dict) -> None:
    path = _root_artifacts(root) / JOURNAL_NAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot) + "\n")


def _active_count(loops: dict[str, dict]) -> int:
    return sum(1 for state in loops.values() if state.get("alive"))


def checkin_green(root: Path, loops: dict[str, dict], job_names: list[str]) -> list[str]:
    """Auto source control: commit every green loop so passing work is never
    lost. Idempotent — only loops whose files changed are actually committed."""

    saved: list[str] = []
    for name in job_names:
        state = loops.get(name, {})
        if not state.get("green"):
            continue
        workspace = state.get("workspace") or str(orchestrator.workspace_for(name, root))
        try:
            result = checkin.checkin_green(Path(workspace), name, state.get("build", 0))
        except OSError:
            continue
        if result.get("committed"):
            saved.append(f"{name}@{result.get('sha')}")
    if saved:
        chat.post(root, "system", "keeper: checked in " + ", ".join(saved))
    return saved


def keep_once(root: Path, launch: bool = True) -> Plan:
    """Run one keeper cycle: launch pending work (up to the concurrency cap)
    or post a fresh audit when everything is green."""

    job_names = [job.name for job in orchestrator.list_jobs()]
    loops = _loops_by_name(root)
    plan = make_plan(loops, job_names)
    _append_journal(root, journal_snapshot(loops, job_names))
    checkin_green(root, loops, job_names)
    if plan.pending and launch:
        slots = _max_active() - _active_count(loops)
        started: list[str] = []
        for name in rotate_pending(plan.pending, root)[: max(0, slots)]:
            try:
                orchestrator.launch_loop(
                    name, model=_keeper_model(), forever=False, root=root,
                    attempts=_attempts_per_turn(),
                )
                _record_launch(root, name)
                started.append(name)
            except (RuntimeError, KeyError, OSError):
                continue
        if started:
            chat.post(root, "system", "keeper: launched " + ", ".join(started))
    if plan.all_green and plan.audit is not None:
        signature = _audit_signature(loops, job_names)
        if not _already_audited(root, signature):
            chat.post(root, "loop", plan.audit)
            _remember_audit(root, signature)
    return plan


def _lock_is_alive(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        pid = int(path.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def acquire_lock(root: Path) -> bool:
    """Claim single-instance ownership; False if another keeper is alive."""

    path = _root_artifacts(root) / LOCK_NAME
    if _lock_is_alive(path):
        return False
    path.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _recovery_threshold() -> int:
    try:
        return max(1, int(os.getenv("QAYMARK_UNHEALTHY_LIMIT", "2")))
    except ValueError:
        return 2


def _stall_window() -> float:
    """Seconds of zero progress before we probe/recover. Must exceed one
    attempt's generation deadline so a slow-but-working loop is never flagged."""

    try:
        return max(120.0, float(os.getenv("QAYMARK_STALL_WINDOW", "360")))
    except ValueError:
        return 360.0


def health_cycle(root: Path, unhealthy_streak: int) -> int:
    """Probe health; recover after enough consecutive unhealthy cycles.

    Returns the updated consecutive-unhealthy count.
    """

    report = health.check(root, _base_url(), _model(), _stall_window())
    if report.healthy:
        return 0
    streak = unhealthy_streak + 1
    print(f"keeper: unhealthy ({report.detail}), strike {streak}", flush=True)
    if streak >= _recovery_threshold():
        print("keeper: rebooting into a clean working mode...", flush=True)
        result = health.recover(root)
        chat.post(root, "system",
                  f"keeper: recovered — killed {result['killed']}; {result['runtime']}")
        return 0
    return streak


def run_forever(root: Path | None = None, interval: float = 20.0) -> int:
    """Keep the factory working forever; resilient to per-cycle errors and to a
    wedged Ollama (aggressive health checks + self-healing recovery)."""

    root = (root or factory_root()).resolve()
    if not acquire_lock(root):
        print("keeper: another keeper is already running; exiting", flush=True)
        return 0
    print(f"keeper: watching {root} every {interval:g}s", flush=True)
    unhealthy = 0
    while True:
        try:
            unhealthy = health_cycle(root, unhealthy)
            plan = keep_once(root)
            if plan.pending:
                print("keeper: pending " + ", ".join(plan.pending), flush=True)
            elif plan.all_green:
                print("keeper: all green — audited, watching for new work", flush=True)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            print(f"keeper: cycle error (continuing): {exc}", flush=True)
        time.sleep(interval)
