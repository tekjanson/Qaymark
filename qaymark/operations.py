"""Apply model file operations safely inside the workspace."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OperationOutcome:
    written: list[str] = field(default_factory=list)
    created_dirs: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def safe_target(root: Path, rel_path: str) -> Path | None:
    """Resolve *rel_path* under *root*, rejecting traversal and absolute escapes."""

    if not rel_path or not isinstance(rel_path, str):
        return None
    candidate = Path(rel_path)
    if candidate.is_absolute():
        return None
    resolved = (root / candidate).resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        return None
    return resolved


def _content_from_operation(operation: dict[str, Any]) -> str | None:
    content = operation.get("content")
    if content is not None:
        return str(content)
    lines = operation.get("lines")
    if isinstance(lines, list):
        joined = "\n".join(str(line) for line in lines)
        return joined + "\n" if lines else joined
    return None


def _do_mkdir(root: Path, operation: dict[str, Any], outcome: OperationOutcome) -> None:
    target = safe_target(root, operation.get("path", ""))
    if target is None:
        outcome.skipped.append(f"unsafe mkdir path: {operation.get('path')!r}")
        return
    target.mkdir(parents=True, exist_ok=True)
    outcome.created_dirs.append(str(target.relative_to(root)))


def _do_write(root: Path, operation: dict[str, Any], outcome: OperationOutcome) -> None:
    target = safe_target(root, operation.get("path", ""))
    if target is None:
        outcome.skipped.append(f"unsafe write path: {operation.get('path')!r}")
        return
    content = _content_from_operation(operation)
    if content is None:
        outcome.skipped.append(f"write_file missing content: {operation.get('path')!r}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    outcome.written.append(str(target.relative_to(root)))


def _do_command(
    root: Path, operation: dict[str, Any], outcome: OperationOutcome, allow: bool
) -> None:
    command = operation.get("command")
    if not command:
        return
    if not allow:
        outcome.skipped.append(f"run_command disabled (HARNESS_ALLOW_COMMANDS=0): {command}")
        return
    result = subprocess.run(
        command, cwd=root, shell=True, capture_output=True, text=True, timeout=600, check=False
    )
    outcome.commands.append(
        {"command": command, "returncode": result.returncode, "stderr": result.stderr[:500]}
    )


def apply_operations(
    root: Path, payload: dict[str, Any], allow_commands: bool = False
) -> OperationOutcome:
    """Apply every operation in *payload*, constrained to *root*."""

    outcome = OperationOutcome()
    for operation in payload.get("operations", []):
        if not isinstance(operation, dict):
            outcome.skipped.append(f"non-object operation: {operation!r}")
            continue
        kind = operation.get("kind")
        if kind == "mkdir":
            _do_mkdir(root, operation, outcome)
        elif kind == "write_file":
            _do_write(root, operation, outcome)
        elif kind == "run_command":
            _do_command(root, operation, outcome, allow_commands)
        else:
            outcome.skipped.append(f"unknown operation kind: {kind!r}")
    return outcome
