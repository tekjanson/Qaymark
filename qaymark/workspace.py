"""Workspace inspection: file iteration, snapshotting, and ignore setup."""

from __future__ import annotations

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


def _snippet(path: Path, rel: Path, max_lines: int) -> str:
    if path.suffix.lower() not in TEXT_EXTENSIONS or path.stat().st_size >= 200_000:
        return f"=== {rel} ===\n<binary or too large>\n"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return f"=== {rel} ===\n<unreadable>\n"
    lines = text.splitlines()[:max_lines]
    return f"=== {rel} ===\n" + "\n".join(lines) + "\n"


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
