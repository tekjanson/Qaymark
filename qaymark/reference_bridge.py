"""Reference bridge backed by the drift-be-gone understanding map.

Replaces the old idud Rust binary with a pure-Python sibling framework: it runs
`drift map` over the workspace to produce the "what exists / what to touch"
artifact the harness folds into feedback.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReferenceResult:
    available: bool = False
    summary: str = ""
    brief: str = ""
    notable_files: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    error: str | None = None


def _parse_artifact(artifact: dict[str, Any]) -> ReferenceResult:
    return ReferenceResult(
        available=True,
        summary=str(artifact.get("summary", "")),
        brief=str(artifact.get("synthetic_brief", "")),
        notable_files=[str(f) for f in artifact.get("notable_files", [])][:15],
        domains=[str(d) for d in artifact.get("inferred_domains", [])][:8],
        node_count=len(artifact.get("graph_nodes", [])),
        edge_count=len(artifact.get("graph_edges", [])),
    )


def run_map(drift_src: Path, workspace: Path, output_path: Path) -> ReferenceResult:
    """Generate a drift understanding map for *workspace* and summarise it."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "drift.cli", "map", str(workspace)]
    cmd += ["--output", str(output_path)]
    env = {"PYTHONPATH": str(drift_src)}
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, check=False, env=_env(env)
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ReferenceResult(error=str(exc))
    if result.returncode != 0:
        return ReferenceResult(error=result.stderr[:300] or "drift map failed")
    try:
        artifact = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ReferenceResult(error=f"could not read drift map: {exc}")
    return _parse_artifact(artifact)


def _env(overrides: dict[str, str]) -> dict[str, str]:
    import os

    merged = dict(os.environ)
    merged.update(overrides)
    return merged


def format_reference_feedback(result: ReferenceResult) -> str:
    if not result.available:
        detail = f" ({result.error})" if result.error else ""
        return f"drift reference unavailable{detail}; proceed with structural care."
    lines = [
        "drift reference (what exists / what to touch):",
        f"  - Summary: {result.summary}",
        f"  - Graph: {result.node_count} nodes, {result.edge_count} edges.",
    ]
    if result.domains:
        lines.append(f"  - Domains: {', '.join(result.domains)}.")
    if result.notable_files:
        lines.append(f"  - Notable files: {', '.join(result.notable_files)}.")
    return "\n".join(lines)
