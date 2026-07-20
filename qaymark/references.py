"""Provision the real slop-be-gone and drift-be-gone tools in a shared cache."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import DRIFT_REPO_URL, SLOP_REPO_URL


def _run(
    cmd: list[str], cwd: Path | None = None, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def _refresh_disabled() -> bool:
    return os.getenv("QAYMARK_NO_REFRESH") not in (None, "", "0")


def ensure_repo(url: str, dest: Path) -> bool:
    """Clone *url* into *dest*, or fast-forward it if already present."""

    dest.parent.mkdir(parents=True, exist_ok=True)
    if (dest / ".git").exists():
        if not _refresh_disabled():
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


def ensure_drift_src(cache_dir: Path) -> Path | None:
    """Return the importable root of drift-be-gone, cloning if needed.

    drift-be-gone is pure Python, so there is no build step (unlike the old
    Rust idud tool): the clone root has an importable ``drift`` package.
    """

    clone = cache_dir / "drift-be-gone"
    if not ensure_repo(DRIFT_REPO_URL, clone):
        return None
    return clone if (clone / "drift").is_dir() else None
