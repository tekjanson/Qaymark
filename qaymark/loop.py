"""Orchestration: one-shot generation gated by hygiene + idud feedback."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import HarnessConfig
from .hygiene import HygieneResult, fallback_scan, run_sbg
from .idud_bridge import IdudResult, run_idud
from .jsonio import extract_json_payload
from .ollama_client import chat
from .operations import apply_operations
from .prompt import build_system_prompt, build_user_prompt, load_rule_digest, synthesize_feedback
from .references import ensure_idud_binary, ensure_slop_src
from .report import AttemptReport
from .workspace import ensure_sbgignore, iter_files, seed_workspace, summarize_workspace


@dataclass
class Tools:
    slop_src: Path | None
    idud_binary: Path | None


def fallback_operations(task: str) -> list[dict[str, object]]:
    """A hygiene-clean stub used only when the model returns no operations."""

    del task  # Kept generic so user task text can never trip a hygiene rule.
    return [
        {
            "kind": "write_file",
            "path": "solution.py",
            "lines": [
                '"""Auto-generated starter module."""',
                "",
                "",
                "def main() -> None:",
                '    """Entry point for the generated solution."""',
                "    return None",
                "",
                "",
                'if __name__ == "__main__":',
                "    main()",
            ],
        }
    ]


def provision(config: HarnessConfig) -> Tools:
    slop_src = ensure_slop_src(config.cache_dir)
    idud_binary = ensure_idud_binary(config.cache_dir) if config.use_idud else None
    return Tools(slop_src=slop_src, idud_binary=idud_binary)


def run_validation(root: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=root, shell=True, capture_output=True, text=True, timeout=600, check=False
    )


def run_hygiene(config: HarnessConfig, tools: Tools) -> HygieneResult:
    if tools.slop_src is not None:
        return run_sbg(config.workspace, config.manifest_path, tools.slop_src, config.strict)
    return fallback_scan(config.workspace, iter_files(config.workspace))


def run_reference(config: HarnessConfig, tools: Tools) -> IdudResult:
    if tools.idud_binary is None:
        return IdudResult(error="idud disabled or unavailable")
    output = config.artifact_dir() / "idud_understanding.json"
    return run_idud(tools.idud_binary, config.workspace, output)


def _generate(config: HarnessConfig, system: str, user: str) -> dict[str, object]:
    response = chat(system, user, config.model, config.base_url, config.request_timeout)
    try:
        payload = extract_json_payload(response)
    except ValueError:
        payload = {"summary": "fallback: unparseable model output", "operations": []}
    if not payload.get("operations"):
        ops = fallback_operations(config.task)
        payload = {"summary": "fallback: no operations returned", "operations": ops}
    return payload


def _persist(config: HarnessConfig, report: AttemptReport, payload: dict[str, object]) -> None:
    artifact_dir = config.artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "attempt": report.attempt,
        "summary": payload.get("summary"),
        "validation_ok": report.validation_ok,
        "hygiene_passed": report.hygiene.passed,
        "hygiene_degraded": report.hygiene.degraded,
        "violation_count": len(report.hygiene.violations),
        "idud_available": report.idud.available,
        "written": report.operations.written,
        "skipped": report.operations.skipped,
    }
    path = artifact_dir / f"run-attempt-{report.attempt}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")


def _attempt(
    config: HarnessConfig, tools: Tools, system: str, feedback: str | None, attempt: int
) -> AttemptReport:
    snapshot = summarize_workspace(config.workspace)
    user = build_user_prompt(config.task, config.validation_command, snapshot, feedback)
    payload = _generate(config, system, user)
    outcome = apply_operations(config.workspace, payload, config.allow_commands, config.protected)
    ensure_sbgignore(config.workspace)
    validation = run_validation(config.workspace, config.validation_command)
    hygiene = run_hygiene(config, tools)
    idud = run_reference(config, tools)
    validation_output = (validation.stdout + "\n" + validation.stderr).strip()
    ok = validation.returncode == 0
    report = AttemptReport(attempt, ok, validation_output, hygiene, idud, outcome)
    _persist(config, report, payload)
    return report


def run_harness(config: HarnessConfig) -> int:
    """Run the guardrailed loop; return 0 on success, non-zero otherwise."""

    config.workspace.mkdir(parents=True, exist_ok=True)
    config.protected = frozenset(seed_workspace(config.workspace, config.seed_dir))
    ensure_sbgignore(config.workspace)
    tools = provision(config)
    system = build_system_prompt(load_rule_digest(config.manifest_path))
    feedback: str | None = None

    for attempt in range(1, config.max_attempts + 1):
        print(f"== attempt {attempt}/{config.max_attempts} ==", flush=True)
        try:
            report = _attempt(config, tools, system, feedback, attempt)
        except OSError as exc:
            print(f"harness attempt failed: {exc}", file=sys.stderr)
            return 2
        if report.passed():
            print(f"✅ guardrails passed on attempt {attempt}", flush=True)
            return 0
        feedback = synthesize_feedback(report)
        print(feedback, flush=True)

    print("harness reached the maximum number of guardrailed attempts", file=sys.stderr)
    return 1
