"""The plan a workspace is working on — visible, editable, and steering.

Each loop keeps a small plan under ``.harness/plan.json``: a goal, an ordered
list of steps (each pending / active / done / blocked), and a free-text focus
note the loop writes to say what it is doing right now. The operator can edit any
of it from the console, and the plan is folded into the model's prompt, so
editing the plan actually adjusts the workspace's direction as it runs.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from dataclasses import dataclass

from .config import ARTIFACT_DIR_NAME
from .jsonio import extract_json_payload
from .ollama_client import chat as ollama_chat

PLAN_FILE = "plan.json"
STATUSES = ("pending", "active", "done", "blocked")
_DEFAULT_STEPS = (
    "Generate a working change for the task",
    "Make the validation command pass",
    "Clear the strict hygiene gate",
    "Land a green build",
)


@dataclass(frozen=True)
class PlanSeed:
    task: str
    snapshot: str
    rule_digest: str
    model: str
    base_url: str
    timeout: int = 600


def plan_path(workspace: Path) -> Path:
    return workspace / ARTIFACT_DIR_NAME / PLAN_FILE


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def read_plan(workspace: Path) -> dict:
    path = plan_path(workspace)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_plan(workspace: Path, plan: dict) -> dict:
    plan["updated_at"] = _stamp()
    path = plan_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def _new_step(text: str, status: str = "pending") -> dict:
    return {"id": f"s{uuid.uuid4().hex[:10]}", "text": text.strip(), "status": status}


def _normalize_steps(raw_steps: object) -> list[dict]:
    if not isinstance(raw_steps, list):
        return []
    steps: list[dict] = []
    for raw in raw_steps[:6]:
        text = ""
        status = "pending"
        if isinstance(raw, str):
            text = raw.strip()
        elif isinstance(raw, dict):
            text = str(raw.get("text") or raw.get("step") or raw.get("title") or "").strip()
            status = str(raw.get("status") or "pending").strip().lower()
        if not text:
            continue
        if status not in STATUSES:
            status = "pending"
        steps.append(_new_step(text, status))
    if steps and not any(step["status"] == "active" for step in steps):
        steps[0]["status"] = "active"
    return steps


def _default_plan(goal: str) -> dict:
    steps = [_new_step(text) for text in _DEFAULT_STEPS]
    if steps:
        steps[0]["status"] = "active"
    return {"goal": goal.strip(), "steps": steps, "focus_note": "", "generated_by": "fallback"}


def _plan_system_prompt(rule_digest: str) -> str:
    return (
        "You generate the governing plan for a local coding workspace.\n"
        "Return ONLY a JSON object with exactly these keys: goal, focus_note, steps.\n"
        "goal should be a short sentence. focus_note should describe the current\n"
        "focus in plain language. steps should be 3 to 6 concrete steps, each a\n"
        "short string or an object with text and optional status.\n\n"
        "The plan must keep the loop on the smallest safe chunk, prefer visible\n"
        "progress, and avoid vague or lazy steps.\n\n"
        f"Active hygiene rules: {rule_digest or 'slop-be-gone default hygiene rules'}."
    )


def _plan_user_prompt(task: str, snapshot: str) -> str:
    return (
        f"Task:\n{task}\n\n"
        f"Workspace snapshot:\n{snapshot or 'No workspace snapshot available.'}\n\n"
        "Create the plan JSON now."
    )


def generate_plan(seed: PlanSeed) -> dict | None:
    try:
        response = ollama_chat(
            _plan_system_prompt(seed.rule_digest),
            _plan_user_prompt(seed.task, seed.snapshot),
            seed.model,
            seed.base_url,
            seed.timeout,
        )
        payload = extract_json_payload(response)
    except (OSError, ValueError, TypeError):
        return None
    goal = str(payload.get("goal") or seed.task or "Deliver the task").strip()
    focus_note = str(payload.get("focus_note") or "").strip()
    steps = _normalize_steps(payload.get("steps"))
    if not steps:
        return None
    return {
        "goal": goal,
        "focus_note": focus_note,
        "steps": steps,
        "generated_by": "ollama",
        "generated_at": _stamp(),
    }


def ensure_plan(workspace: Path, goal: str) -> dict:
    """Create a default plan the first time a loop runs; keep any existing one."""

    plan = read_plan(workspace)
    if plan.get("steps"):
        return plan
    return write_plan(workspace, _default_plan(goal))


def bootstrap_plan(workspace: Path, goal: str, seed: PlanSeed) -> dict:
    """Seed the governing plan from the model, falling back to defaults."""

    plan = read_plan(workspace)
    if plan.get("steps"):
        return plan
    generated = generate_plan(seed)
    if generated is None:
        return write_plan(workspace, _default_plan(goal))
    return write_plan(workspace, generated)


def set_goal(workspace: Path, goal: str) -> dict:
    plan = read_plan(workspace)
    plan["goal"] = goal.strip()
    return write_plan(workspace, plan)


def set_focus_note(workspace: Path, note: str) -> dict:
    plan = read_plan(workspace)
    plan["focus_note"] = note.strip()
    return write_plan(workspace, plan)


def add_step(workspace: Path, text: str) -> dict:
    plan = read_plan(workspace)
    steps = plan.setdefault("steps", [])
    if text.strip():
        steps.append(_new_step(text))
    return write_plan(workspace, plan)


def remove_step(workspace: Path, step_id: str) -> dict:
    plan = read_plan(workspace)
    plan["steps"] = [s for s in plan.get("steps", []) if s.get("id") != step_id]
    return write_plan(workspace, plan)


def update_step(workspace: Path, step_id: str, text: str | None, status: str | None) -> dict:
    plan = read_plan(workspace)
    for step in plan.get("steps", []):
        if step.get("id") != step_id:
            continue
        if text is not None and text.strip():
            step["text"] = text.strip()
        if status in STATUSES:
            step["status"] = status
    return write_plan(workspace, plan)


def set_active(workspace: Path, step_id: str) -> dict:
    """Mark one step active (the operator's focus) and demote other active ones."""

    plan = read_plan(workspace)
    for step in plan.get("steps", []):
        if step.get("id") == step_id:
            step["status"] = "active"
        elif step.get("status") == "active":
            step["status"] = "pending"
    return write_plan(workspace, plan)


def active_step(plan: dict) -> dict | None:
    for step in plan.get("steps", []):
        if step.get("status") == "active":
            return step
    return None


def plan_prompt_text(plan: dict) -> str:
    """Render the plan as guidance folded into the model prompt."""

    if not plan:
        return ""
    lines = []
    source = plan.get("generated_by")
    if source:
        label = str(source)
        generated_at = plan.get("generated_at")
        if generated_at:
            label = f"{label} at {generated_at}"
        lines.append(f"Plan source: {label}")
    goal = plan.get("goal")
    if goal:
        lines.append(f"Plan goal: {goal}")
    current = active_step(plan)
    if current:
        lines.append(f"Focus now on this step: {current.get('text', '')}")
    steps = plan.get("steps", [])
    if steps:
        lines.append("Full plan:")
        for step in steps:
            mark = {"done": "x", "active": ">", "blocked": "!"}.get(step.get("status"), " ")
            lines.append(f"  [{mark}] {step.get('text', '')}")
    return "\n".join(lines)
