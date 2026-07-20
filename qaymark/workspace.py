"""Workspace inspection: file iteration, snapshotting, and ignore setup."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import ARTIFACT_DIR_NAME, IGNORE_NAMES

TEXT_EXTENSIONS = frozenset(
    {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".sh",
        ".js",
        ".mjs",
        ".ts",
        ".html",
        ".css",
        ".rs",
        ".go",
    }
)

_SBGIGNORE_ENTRIES = (
    "context/",
    f"{ARTIFACT_DIR_NAME}/",
    ".git/",
    ".venv/",
    "venv/",
    "node_modules/",
    "target/",
    "__pycache__/",
)


def is_ignored(path: Path) -> bool:
    return any(part in IGNORE_NAMES for part in path.parts)


def iter_files(root: Path) -> list[Path]:
    files = [p for p in root.rglob("*") if p.is_file() and not is_ignored(p.relative_to(root))]
    return sorted(files)


def _is_contract_file(rel: Path) -> bool:
    """Acceptance tests/specs are the contract; the model must see them whole."""

    name = rel.name.lower()
    return "test" in name or "spec" in name or name == "task.md"


def _snippet(path: Path, rel: Path, max_lines: int) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS or path.stat().st_size >= 200_000:
        return f"=== {rel} ===\n<binary or too large>\n"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return f"=== {rel} ===\n<unreadable>\n"
    # Show acceptance tests/specs in full — they define exactly what to build,
    # so truncating them to a preview makes the task impossible to satisfy.
    limit = 400 if _is_contract_file(rel) else max_lines
    lines = text.splitlines()
    body = lines[:limit]
    suffix = "" if len(lines) <= limit else f"\n... ({len(lines) - limit} more lines)"
    label = f"=== {rel} (contract — full) ===" if _is_contract_file(rel) else f"=== {rel} ==="
    return f"{label}\n" + "\n".join(body) + suffix + "\n"


def summarize_workspace(root: Path, file_limit: int = 40, line_limit: int = 30) -> str:
    files = iter_files(root)
    if not files:
        return "<empty workspace>"
    parts = [_snippet(path, path.relative_to(root), line_limit) for path in files[:file_limit]]
    return "\n".join(parts)


def ensure_sbgignore(root: Path) -> None:
    """Write a .sbgignore so the hygiene gate skips refs and build artifacts."""

    target = root / ".sbgignore"
    header = "# Managed by the local coding harness.\n"
    body = "\n".join(_SBGIGNORE_ENTRIES) + "\n"
    desired = header + body
    if target.exists() and target.read_text(encoding="utf-8") == desired:
        return
    target.write_text(desired, encoding="utf-8")


def seed_workspace(root: Path, seed_dir: Path | None) -> list[str]:
    """Copy seed_dir's files into the workspace, returning their rel paths.

    Used to plant the fixed spec and acceptance tests. The returned paths are
    treated as protected so generated operations cannot overwrite them.
    """

    if seed_dir is None:
        return []
    seeded: list[str] = []
    for src in sorted(seed_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(seed_dir)
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        seeded.append(rel.as_posix())
    return seeded
