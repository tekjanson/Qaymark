"""Hygiene gate backed by the real slop-be-gone (sbg) engine."""

from __future__ import annotations

import ast
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HygieneResult:
    passed: bool
    violations: list[dict[str, Any]] = field(default_factory=list)
    degraded: bool = False
    error: str | None = None


def _sbg_command(workspace: Path, manifest: Path, strict: bool) -> list[str]:
    cmd = ["python3", "-m", "sbg.cli", "check", str(workspace)]
    cmd += ["--json", "--manifest", str(manifest)]
    if strict:
        cmd.append("--strict")
    return cmd


def run_sbg(workspace: Path, manifest: Path, src_dir: Path, strict: bool = True) -> HygieneResult:
    """Run the real sbg engine and parse its JSON violation report."""

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(src_dir), env.get("PYTHONPATH", "")]))
    try:
        result = subprocess.run(
            _sbg_command(workspace, manifest, strict),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return HygieneResult(passed=False, degraded=True, error=str(exc))

    try:
        violations = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        message = result.stderr[:300] or "bad sbg output"
        return HygieneResult(passed=False, degraded=True, error=message)
    return HygieneResult(passed=result.returncode == 0, violations=violations)


def _violation(rule_id: str, rel: str, message: str, line: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"rule_id": rule_id, "path": rel, "message": message}
    payload["severity"] = "error"
    if line is not None:
        payload["line"] = line
    return payload


def _python_syntax_issue(text: str, path: Path, rel: str) -> list[dict[str, Any]]:
    if path.suffix != ".py":
        return []
    try:
        ast.parse(text)
    except SyntaxError as exc:
        return [_violation("python-syntax", rel, exc.msg or "syntax error", exc.lineno)]
    return []


def _fallback_scan_file(path: Path, rel: str) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        return [_violation("empty-files", rel, "file is empty")]
    issues: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        if line.endswith((" ", "\t")):
            issues.append(_violation("trailing-whitespace", rel, "trailing whitespace", index))
        if len(line) > 100:
            issues.append(_violation("long-lines", rel, "line exceeds 100 chars", index))
    if not text.endswith("\n"):
        issues.append(_violation("final-newline", rel, "missing final newline"))
    issues.extend(_python_syntax_issue(text, path, rel))
    return issues


def fallback_scan(workspace: Path, files: list[Path]) -> HygieneResult:
    """Minimal degraded hygiene gate used only when sbg is unavailable."""

    violations: list[dict[str, Any]] = []
    for path in files:
        violations.extend(_fallback_scan_file(path, path.relative_to(workspace).as_posix()))
    return HygieneResult(passed=not violations, violations=violations, degraded=True)


def format_hygiene_feedback(result: HygieneResult, limit: int = 12) -> str:
    if result.error:
        return f"Hygiene gate could not run ({result.error}); relying on degraded checks."
    if not result.violations:
        return "Hygiene gate: no violations."
    prefix = "Hygiene gate (degraded fallback)" if result.degraded else "Hygiene gate"
    lines = [f"{prefix} found {len(result.violations)} violation(s):"]
    for violation in result.violations[:limit]:
        location = violation.get("path", "?")
        if violation.get("line") is not None:
            location = f"{location}:{violation['line']}"
        rule_id = violation.get("rule_id", "?")
        message = violation.get("message", "")
        lines.append(f"  - [{rule_id}] {location}: {message}")
    return "\n".join(lines)
