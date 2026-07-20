"""Local loop orchestrator: the control tower for the code factory.

This is the layer that lets a human *decide which loops run* and manage them
without Copilot. It knows two things:

- **Jobs** — the fixed specs under ``jobs/`` (a ``TASK.md`` plus optional
  ``seed/``, ``starter/``, and a ``job.json`` manifest).
- **Loops** — supervised workspaces under the persistent factory root, each with
  a live status, a control channel, and (when running) a supervisor process.

The orchestrator can list jobs, launch a loop for a job into a persistent
workspace, and inspect/steer every loop (pause, resume, redirect, stop). It is
pure local process management — no network, no daemon, no external services.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import control
from .config import ARTIFACT_DIR_NAME, REPO_ROOT, factory_root

JOBS_DIR = REPO_ROOT / "jobs"
_HARNESS_ENTRY = REPO_ROOT / "scripts" / "code_harness.py"
_DEFAULT_VALIDATION = "python3 -m compileall -q ."


@dataclass(frozen=True)
class Job:
    name: str
    description: str
    task: str
    validation: str
    model: str | None
    max_attempts: int
    seed: Path | None
    starter: Path | None


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_job(job_dir: Path) -> Job | None:
    task_path = job_dir / "TASK.md"
    if not task_path.is_file():
        return None
    manifest = _read_json(job_dir / "job.json")
    seed = job_dir / "seed"
    starter = job_dir / "starter"
    return Job(
        name=job_dir.name,
        description=str(manifest.get("description", "")),
        task=task_path.read_text(encoding="utf-8"),
        validation=str(manifest.get("validation", _DEFAULT_VALIDATION)),
        model=(str(manifest["model"]) if manifest.get("model") else None),
        max_attempts=int(manifest.get("max_attempts", 8)),
        seed=seed if seed.is_dir() else None,
        starter=starter if starter.is_dir() else None,
    )


def list_jobs() -> list[Job]:
    if not JOBS_DIR.is_dir():
        return []
    jobs = [_load_job(child) for child in sorted(JOBS_DIR.iterdir()) if child.is_dir()]
    return [job for job in jobs if job is not None]


def get_job(name: str) -> Job | None:
    job_dir = JOBS_DIR / name
    return _load_job(job_dir) if job_dir.is_dir() else None


def workspace_for(name: str, root: Path | None = None) -> Path:
    return (root or factory_root()) / name


def _discover_workspaces(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found = [
        path.parent.parent
        for path in root.rglob("status.json")
        if path.parent.name == ARTIFACT_DIR_NAME
    ]
    return sorted(set(found))


def _loop_phase(workspace: Path) -> dict:
    status_path = workspace / ARTIFACT_DIR_NAME / "status.json"
    return _read_json(status_path)


def _latest_attempt(workspace: Path) -> dict:
    files = sorted((workspace / ARTIFACT_DIR_NAME).glob("run-attempt-*.json"))
    return _read_json(files[-1]) if files else {}


def is_green(workspace: Path) -> bool:
    """A loop is green when its last completed build passed every gate.

    A durable ``green.json`` marker (written on pass, cleared on redirect) keeps
    a reverted-to-last-good workspace green even when the live status has since
    moved to ``watching``/``reverted`` and the newest attempt record failed.
    """

    if (workspace / ARTIFACT_DIR_NAME / "green.json").exists():
        return True
    if _loop_phase(workspace).get("phase") == "passed":
        return True
    attempt = _latest_attempt(workspace)
    return bool(attempt.get("validation_ok")) and bool(attempt.get("hygiene_passed"))


def loop_state(workspace: Path, root: Path | None = None) -> dict:
    """A JSON-friendly snapshot of one loop: status + control + liveness."""

    root = root or factory_root()
    status = _loop_phase(workspace)
    command = control.read_control(workspace)
    try:
        name = workspace.relative_to(root).as_posix()
    except ValueError:
        name = workspace.name
    return {
        "name": name,
        "workspace": str(workspace),
        "phase": str(status.get("phase", "idle")),
        "attempt": status.get("attempt"),
        "max_attempts": status.get("max_attempts"),
        "build": status.get("build", 0),
        "alive": control.loop_is_alive(workspace),
        "pid": control.read_pidfile(workspace),
        "green": is_green(workspace),
        "paused": command.paused,
        "stopping": command.stop,
        "redirect_task": command.redirect_task,
        "note": command.note,
    }


def list_loops(root: Path | None = None) -> list[dict]:
    root = root or factory_root()
    return [loop_state(workspace, root) for workspace in _discover_workspaces(root)]


def _launch_command(
    job: Job, workspace: Path, model: str | None, forever: bool,
    attempts: int | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(_HARNESS_ENTRY),
        "--task",
        job.task,
        "--workspace",
        str(workspace),
        "--validation-command",
        job.validation,
        "--max-attempts",
        str(attempts if attempts and attempts > 0 else job.max_attempts),
        "--supervise",
    ]
    if job.seed is not None:
        command += ["--seed", str(job.seed)]
    if job.starter is not None:
        command += ["--starter", str(job.starter)]
    chosen = model or job.model
    if chosen:
        command += ["--model", chosen]
    if forever:
        command.append("--forever")
    return command


def launch_loop(
    name: str, model: str | None = None, forever: bool = False, root: Path | None = None,
    attempts: int | None = None,
) -> int:
    """Start a supervised loop for *name* as a detached local process.

    Returns the child PID. Refuses to start a second loop for a workspace that
    already has a live supervisor. When *forever* is false the loop yields after
    *attempts* (or the job default) tries, so no single job can monopolise a
    shared worker slot forever.
    """

    job = get_job(name)
    if job is None:
        raise KeyError(f"unknown job: {name}")
    workspace = workspace_for(name, root)
    if control.loop_is_alive(workspace):
        raise RuntimeError(f"loop '{name}' is already running")
    workspace.mkdir(parents=True, exist_ok=True)
    control.write_control(workspace, control.LoopControl())
    log = (workspace / ARTIFACT_DIR_NAME / "supervisor.log").open("a", encoding="utf-8")
    command = _launch_command(job, workspace, model, forever, attempts)
    process = subprocess.Popen(
        command, cwd=str(REPO_ROOT), stdout=log, stderr=log, start_new_session=True
    )
    control.write_pidfile(workspace, process.pid)
    return process.pid


def launch_pending(
    model: str | None = None, forever: bool = True, root: Path | None = None
) -> list[str]:
    """Start a loop for every job that is neither green nor already running.

    This realises "always trying if it isn't green": non-green loops all get a
    supervisor, and the factory turn ensures they run one-at-a-time, not all at
    once. Defaults to ``forever`` so a launched loop keeps trying until green.
    """

    started: list[str] = []
    for job in list_jobs():
        workspace = workspace_for(job.name, root)
        if control.loop_is_alive(workspace) or is_green(workspace):
            continue
        launch_loop(job.name, model=model, forever=forever, root=root)
        started.append(job.name)
    return started


def pause_loop(name: str, note: str = "", root: Path | None = None) -> dict:
    return control.pause(workspace_for(name, root), note).to_dict()


def resume_loop(name: str, note: str = "", root: Path | None = None) -> dict:
    return control.resume(workspace_for(name, root), note).to_dict()


def stop_loop(name: str, note: str = "", root: Path | None = None) -> dict:
    return control.request_stop(workspace_for(name, root), note).to_dict()


def redirect_loop(name: str, task: str, note: str = "", root: Path | None = None) -> dict:
    return control.redirect(workspace_for(name, root), task, note).to_dict()
