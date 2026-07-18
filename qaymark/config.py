"""Configuration and path resolution for the harness."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "sbg_manifest.json"

SLOP_REPO_URL = "https://github.com/spamApply1/slop-be-gone"
DRIFT_REPO_URL = "https://github.com/spamApply1/drift-be-gone"

# The spamApply1 standards ecosystem — one framework per concern. slop-be-gone
# gates code hygiene; these siblings extend enforcement to design, workflow, and
# architecture (drift-be-gone, which also emits the understanding map).
DESIGN_REPO_URL = "https://github.com/spamApply1/design-be-gone"
WORKFLOW_REPO_URL = "https://github.com/spamApply1/chaos-be-gone"

ARTIFACT_DIR_NAME = ".harness"
IGNORE_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        "target",
        ARTIFACT_DIR_NAME,
    }
)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


_DEFAULT_BASE_URL = "http://localhost:11434"


def default_cache_dir() -> Path:
    override = os.getenv("HARNESS_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    base = os.getenv("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(base) / "local-coding-harness"


@dataclass
class HarnessConfig:
    """Resolved settings for a single harness run."""

    task: str
    workspace: Path
    validation_command: str = "python3 -m compileall -q ."
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b"))
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", _DEFAULT_BASE_URL))
    max_attempts: int = field(default_factory=lambda: _env_int("HARNESS_MAX_ATTEMPTS", 3))
    manifest_path: Path = DEFAULT_MANIFEST
    cache_dir: Path = field(default_factory=default_cache_dir)
    allow_commands: bool = field(default_factory=lambda: _env_flag("HARNESS_ALLOW_COMMANDS", False))
    use_reference: bool = field(
        default_factory=lambda: _env_flag("HARNESS_USE_REFERENCE", True)
    )
    strict: bool = True
    request_timeout: int = field(default_factory=lambda: _env_int("HARNESS_REQUEST_TIMEOUT", 600))
    seed_dir: Path | None = None
    starter_dir: Path | None = None
    protected: frozenset[str] = frozenset()

    def artifact_dir(self) -> Path:
        return self.workspace / ARTIFACT_DIR_NAME
