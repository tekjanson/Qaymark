"""Orchestration: one-shot generation gated by hygiene + reference feedback."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import HarnessConfig
from .hygiene import HygieneResult, fallback_scan, run_sbg
from .jsonio import extract_json_payload
from .ollama_client import chat
from .operations import apply_operations
from .prompt import build_system_prompt, build_user_prompt, load_rule_digest, synthesize_feedback
from .reference_bridge import ReferenceResult, run_map
from .references import ensure_drift_src, ensure_slop_src
from .report import AttemptReport
from .workspace import ensure_sbgignore, iter_files, seed_workspace, summarize_workspace


@dataclass
class Tools:
    slop_src: Path | None
    drift_src: Path | None


def _status_path(config: HarnessConfig) -> Path:
    return config.artifact_dir() / "status.json"


def _feedback_path(config: HarnessConfig) -> Path:
    return config.artifact_dir() / "feedback.txt"


def _load_external_feedback(config: HarnessConfig) -> str | None:
    path = _feedback_path(config)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _merge_feedback(primary: str | None, secondary: str | None) -> str | None:
    if primary and secondary:
        return primary + "\n\n" + secondary
    return primary or secondary


def _rules_path(config: HarnessConfig) -> Path:
    return config.artifact_dir() / "rules.md"


def _load_rules(config: HarnessConfig) -> str | None:
    """Durable, human-defined standards folded into the system prompt."""

    path = _rules_path(config)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _augment_system_with_rules(config: HarnessConfig, system: str) -> str:
    rules = _load_rules(config)
    if not rules:
        return system
    return (
        f"{system}\n\nDurable project rules defined by the operator — always "
        f"follow these, they override defaults:\n{rules}"
    )


def _build_count_path(config: HarnessConfig) -> Path:
    return config.artifact_dir() / "build_count"


def _bump_build_count(config: HarnessConfig) -> int:
    path = _build_count_path(config)
    current = 0
    if path.exists():
        try:
            current = int(path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            current = 0
    current += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(current), encoding="utf-8")
    return current


def _read_build_count(config: HarnessConfig) -> int:
    path = _build_count_path(config)
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip() or "0")
    except ValueError:
        return 0


def _write_status(
    config: HarnessConfig,
    phase: str,
    attempt: int | None = None,
    report: AttemptReport | None = None,
) -> None:
    payload: dict[str, object] = {
        "phase": phase,
        "task": config.task,
        "workspace": str(config.workspace),
        "attempt": attempt,
        "max_attempts": config.max_attempts,
        "build": _read_build_count(config),
    }
    if report is not None:
        payload.update(
            {
                "validation_ok": report.validation_ok,
                "validation_output": report.validation_output,
                "hygiene_passed": report.hygiene.passed,
                "hygiene_degraded": report.hygiene.degraded,
                "hygiene_violations": len(report.hygiene.violations),
                "reference_available": report.reference.available,
                "written": report.operations.written,
                "skipped": report.operations.skipped,
            }
        )
    path = _status_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _fallback_python_solution() -> list[dict[str, object]]:
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


def _fallback_webtetris() -> dict[str, object]:
    return {
        "kind": "write_file",
        "path": "webtetris.py",
        "lines": [
            '"""Python seam for a browser-playable Tetris job."""',
            "",
            "from __future__ import annotations",
            "",
            "from tetris import Tetris",
            "",
            "",
            "def game_state(tetris: Tetris) -> dict:",
            '    raise NotImplementedError("Return a JSON-friendly snapshot.")',
            "",
            "",
            "def apply_action(tetris: Tetris, action: str) -> None:",
            '    raise NotImplementedError("Apply one action to the game.")',
        ],
    }


def _fallback_index_html() -> dict[str, object]:
    return {
        "kind": "write_file",
        "path": "index.html",
        "lines": [
            "<!doctype html>",
            '<html lang="en">',
            "  <head>",
            '    <meta charset="utf-8">',
            '    <meta name="viewport" content="width=device-width, initial-scale=1">',
            "    <title>Qaymark Tetris</title>",
            '    <link rel="stylesheet" href="styles.css">',
            '    <script defer src="app.js"></script>',
            "  </head>",
            "  <body>",
            '    <canvas id="board" width="320" height="640"></canvas>',
            '    <p id="message" role="status"></p>',
            '    <button id="start" type="button" data-action="start">Start</button>',
            '    <button id="pause" type="button" data-action="pause">Pause</button>',
            '    <button id="restart" type="button" data-action="restart">Restart</button>',
            '    <div id="score">0</div>',
            '    <div id="level">1</div>',
            '    <div id="lines">0</div>',
            "  </body>",
            "</html>",
        ],
    }


def _fallback_app_js() -> dict[str, object]:
    return {
        "kind": "write_file",
        "path": "app.js",
        "lines": [
            "const WIDTH = 10;",
            "const HEIGHT = 20;",
            "const CELL = 32;",
            "",
            "function gameState() {",
            '  throw new Error("Implement the browser state snapshot.");',
            "}",
            "",
            "function applyAction() {",
            '  throw new Error("Implement the browser action handler.");',
            "}",
            "",
            'document.getElementById("start").addEventListener("click", () => {});',
            'document.getElementById("pause").addEventListener("click", () => {});',
            'document.getElementById("restart").addEventListener("click", () => {});',
        ],
    }


def _fallback_styles_css() -> dict[str, object]:
    return {
        "kind": "write_file",
        "path": "styles.css",
        "lines": [
            "* {",
            "  box-sizing: border-box;",
            "}",
            "",
            "body {",
            "  margin: 0;",
            "  font-family: system-ui, sans-serif;",
            "}",
        ],
    }


def _fallback_web_solution() -> list[dict[str, object]]:
    return [
        _fallback_webtetris(),
        _fallback_index_html(),
        _fallback_app_js(),
        _fallback_styles_css(),
    ]


def fallback_operations(task: str) -> list[dict[str, object]]:
    """A hygiene-clean stub used only when the model returns no operations."""

    lower = task.lower()
    if any(keyword in lower for keyword in ("web", "browser", "html", "javascript")):
        return _fallback_web_solution()
    return _fallback_python_solution()


def provision(config: HarnessConfig) -> Tools:
    slop_src = ensure_slop_src(config.cache_dir)
    drift_src = ensure_drift_src(config.cache_dir) if config.use_reference else None
    return Tools(slop_src=slop_src, drift_src=drift_src)


def run_validation(root: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=root, shell=True, capture_output=True, text=True, timeout=600, check=False
    )


_PRETTIER_SUFFIXES = (".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".css", ".html", ".json")


def _format_python(root: Path, written: list[str], protected: frozenset[str]) -> None:
    black = shutil.which("black")
    if black is None:
        return
    targets = [f for f in written if f.endswith(".py") and f not in protected]
    if not targets:
        return
    cmd = [black, "-q", "-l", "100", *targets]
    subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120, check=False)


def _format_web(root: Path, written: list[str], protected: frozenset[str]) -> None:
    prettier = shutil.which("prettier")
    if prettier is None:
        return
    targets = [f for f in written if f.endswith(_PRETTIER_SUFFIXES) and f not in protected]
    if not targets:
        return
    cmd = [prettier, "--write", "--print-width", "100", *targets]
    subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120, check=False)


def autoformat(root: Path, written: list[str], protected: frozenset[str]) -> None:
    """Auto-format generated files so style is deterministic before the gate.

    Python is formatted with black and web assets (JS/TS/CSS/HTML/JSON) with
    prettier when those tools are on PATH; missing tools are skipped silently.
    """

    _format_python(root, written, protected)
    _format_web(root, written, protected)


def run_hygiene(config: HarnessConfig, tools: Tools) -> HygieneResult:
    if tools.slop_src is not None:
        return run_sbg(config.workspace, config.manifest_path, tools.slop_src, config.strict)
    return fallback_scan(config.workspace, iter_files(config.workspace))


def run_reference(config: HarnessConfig, tools: Tools) -> ReferenceResult:
    if tools.drift_src is None:
        return ReferenceResult(error="drift reference disabled or unavailable")
    output = config.artifact_dir() / "drift_understanding.json"
    return run_map(tools.drift_src, config.workspace, output)


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
        "reference_available": report.reference.available,
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
    autoformat(config.workspace, outcome.written, config.protected)
    ensure_sbgignore(config.workspace)
    validation = run_validation(config.workspace, config.validation_command)
    hygiene = run_hygiene(config, tools)
    reference = run_reference(config, tools)
    validation_output = (validation.stdout + "\n" + validation.stderr).strip()
    ok = validation.returncode == 0
    report = AttemptReport(attempt, ok, validation_output, hygiene, reference, outcome)
    _persist(config, report, payload)
    return report


def run_harness(config: HarnessConfig) -> int:
    """Run the guardrailed loop; return 0 on success, non-zero otherwise."""

    config.workspace.mkdir(parents=True, exist_ok=True)
    config.protected = frozenset(seed_workspace(config.workspace, config.seed_dir))
    seed_workspace(config.workspace, config.starter_dir)  # starter files stay editable
    ensure_sbgignore(config.workspace)
    tools = provision(config)
    system = build_system_prompt(load_rule_digest(config.manifest_path))
    system = _augment_system_with_rules(config, system)
    feedback: str | None = None
    _write_status(config, "starting")

    for attempt in range(1, config.max_attempts + 1):
        feedback = _merge_feedback(_load_external_feedback(config), feedback)
        _write_status(config, "attempting", attempt)
        print(f"== attempt {attempt}/{config.max_attempts} ==", flush=True)
        try:
            report = _attempt(config, tools, system, feedback, attempt)
        except OSError as exc:
            print(f"attempt {attempt} errored (continuing): {exc}", file=sys.stderr)
            feedback = f"Attempt {attempt} did not finish ({exc}). Regenerate a complete file."
            continue
        if report.passed():
            _bump_build_count(config)
            _write_status(config, "passed", attempt, report)
            print(f"✅ guardrails passed on attempt {attempt}", flush=True)
            return 0
        feedback = synthesize_feedback(report, config.workspace)
        _write_status(config, "retrying", attempt, report)
        print(feedback, flush=True)

    _write_status(config, "failed")
    print("harness reached the maximum number of guardrailed attempts", file=sys.stderr)
    return 1
