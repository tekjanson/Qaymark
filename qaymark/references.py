"""Provision the real slop-be-gone and idud tools in a shared cache."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import IDUD_REPO_URL, SLOP_REPO_URL


def _run(
    cmd: list[str], cwd: Path | None = None, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def ensure_repo(url: str, dest: Path) -> bool:
    """Clone *url* into *dest*, or fast-forward it if already present."""

    dest.parent.mkdir(parents=True, exist_ok=True)
    if (dest / ".git").exists():
        _run(["git", "-C", str(dest), "pull", "--ff-only"])
        return True
    result = _run(["git", "clone", "--depth", "1", url, str(dest)])
    return result.returncode == 0


def ensure_slop_src(cache_dir: Path) -> Path | None:
    """Return the importable src/ dir of slop-be-gone, cloning if needed."""

    clone = cache_dir / "slop-be-gone"
    if not ensure_repo(SLOP_REPO_URL, clone):
        return None
    src = clone / "src"
    return src if (src / "sbg").is_dir() else None


def _idud_binary(clone: Path) -> Path:
    return clone / "target" / "release" / "idud"


def ensure_idud_binary(cache_dir: Path, build: bool = True) -> Path | None:
    """Return the idud release binary, cloning and building it once if needed."""

    clone = cache_dir / "idud"
    if not ensure_repo(IDUD_REPO_URL, clone):
        return None
    binary = _idud_binary(clone)
    if binary.exists():
        return binary
    if not build:
        return None
    result = _run(["cargo", "build", "--release"], cwd=clone, timeout=1800)
    if result.returncode != 0:
        return None
    return binary if binary.exists() else None
