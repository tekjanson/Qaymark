"""Reference bridge backed by the real idud understanding artifact."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IdudResult:
    available: bool = False
    summary: str = ""
    brief: str = ""
    notable_files: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    error: str | None = None


def _parse_artifact(artifact: dict[str, Any]) -> IdudResult:
    return IdudResult(
        available=True,
        summary=str(artifact.get("summary", "")),
        brief=str(artifact.get("synthetic_brief", "")),
        notable_files=[str(f) for f in artifact.get("notable_files", [])][:15],
        domains=[str(d) for d in artifact.get("inferred_domains", [])][:8],
        node_count=len(artifact.get("graph_nodes", [])),
        edge_count=len(artifact.get("graph_edges", [])),
    )


def run_idud(binary: Path, workspace: Path, output_path: Path) -> IdudResult:
    """Generate an idud understanding artifact for *workspace* and summarise it."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(binary), "understand-repo", "--repo-path", str(workspace)]
    cmd += ["--output", str(output_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return IdudResult(error=str(exc))
    if result.returncode != 0:
        return IdudResult(error=result.stderr[:300] or "idud understand-repo failed")
    try:
        artifact = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return IdudResult(error=f"could not read idud artifact: {exc}")
    return _parse_artifact(artifact)


def format_idud_feedback(result: IdudResult) -> str:
    if not result.available:
        detail = f" ({result.error})" if result.error else ""
        return f"idud reference unavailable{detail}; proceed with structural care."
    lines = [
        "idud reference (what exists / what to touch):",
        f"  - Summary: {result.summary}",
        f"  - Graph: {result.node_count} nodes, {result.edge_count} edges.",
    ]
    if result.domains:
        lines.append(f"  - Domains: {', '.join(result.domains)}.")
    if result.notable_files:
        lines.append(f"  - Notable files: {', '.join(result.notable_files)}.")
    return "\n".join(lines)
