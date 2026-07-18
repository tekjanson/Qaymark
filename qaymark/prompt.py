"""Prompt construction and targeted feedback synthesis."""

from __future__ import annotations

import json
from pathlib import Path

from .hygiene import format_hygiene_feedback
from .reference_bridge import format_reference_feedback
from .report import AttemptReport

_SCHEMA = (
    '{"summary": "Brief explanation", "operations": ['
    '{"kind": "mkdir", "path": "some/dir"}, '
    '{"kind": "write_file", "path": "some/dir/file.py", '
    '"lines": ["def main():", "    print(\'hello\')"]}]}'
)


def load_rule_digest(manifest_path: Path, limit: int = 25) -> str:
    """Summarise the active hygiene rules for the system prompt."""

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "slop-be-gone default hygiene rules"
    rules = manifest.get("rules", [])[:limit]
    names = [str(rule.get("id")) for rule in rules if rule.get("enabled", True)]
    return ", ".join(names)


def build_system_prompt(rule_digest: str) -> str:
    """Static contract: role, output schema, and the hygiene bar to clear."""

    return (
        "You are a guardrailed local code generator. You produce a single JSON "
        "action payload; the harness executes it and gates the result.\n\n"
        "Return ONLY a JSON object with exactly two keys: \"summary\" and "
        f"\"operations\". Schema:\n{_SCHEMA}\n\n"
        "Operation kinds: mkdir, write_file (use a \"lines\" array), run_command "
        "(usually disabled). Paths must stay inside the workspace; never use "
        "absolute paths or '..'. Choose real, descriptive paths for the task; "
        "do not copy the placeholder paths from the schema.\n\n"
        "Every file must clear these slop-be-gone rules at error severity:\n"
        f"{rule_digest}.\n"
        "So: no placeholder comments, no deferred-work markers, no empty files, lines "
        "<= 100 chars, no debug artifacts, no secrets, no bare/broad except, no "
        "mutable defaults, no eval/exec; keep functions <= 60 lines, <= 5 args, "
        "and <= 4 levels of nesting. End files with a single newline."
    )


def build_user_prompt(
    task: str, validation_command: str, snapshot: str, feedback: str | None
) -> str:
    """Per-attempt payload: task, validation, workspace state, prior feedback."""

    return (
        f"Task:\n{task}\n\n"
        f"Validation command (must exit 0):\n{validation_command}\n\n"
        f"Workspace snapshot:\n{snapshot}\n\n"
        f"Targeted feedback from the previous attempt:\n{feedback or 'None (first attempt).'}\n\n"
        "Return the JSON action payload now."
    )


def _validation_section(report: AttemptReport) -> str:
    if report.validation_ok:
        return "- Validation: passed."
    return f"- Validation FAILED (fix these first):\n{report.validation_output.strip()[:1600]}"


def synthesize_feedback(report: AttemptReport, root: object = None) -> str:
    """Fuse validation, hygiene, and reference results into next-attempt feedback."""

    parts = [
        f"Attempt {report.attempt} feedback:",
        _validation_section(report),
        format_hygiene_feedback(report.hygiene, root),
        format_reference_feedback(report.reference),
    ]
    if report.operations.skipped:
        skipped = "; ".join(report.operations.skipped[:6])
        parts.append(f"- Skipped operations: {skipped}")
    parts.append(
        "- Next attempt: fix every hygiene violation and validation failure, "
        "keep changes small and explicit, and respect the existing structure."
    )
    return "\n".join(parts)
