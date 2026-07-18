"""Registry and editing layer for the be-gone standards frameworks.

Surfaces every framework's manifest (slop-be-gone, design-be-gone,
chaos-be-gone) as structured rule data the dashboard can drill into and edit, so
the operator can govern the standards that gate the factory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import REPO_ROOT

_SEVERITIES = frozenset({"error", "warning"})
_NUMERIC_FIELDS = frozenset(
    {
        "max_lines",
        "max_args",
        "max_depth",
        "max_length",
        "max_bytes",
        "threshold",
        "max_exports",
    }
)
_META_FIELDS = frozenset({"id", "type", "enabled", "severity", "description", "what", "why"})


@dataclass(frozen=True)
class Framework:
    fid: str
    name: str
    description: str
    manifest: Path
    repo: str


FRAMEWORKS: tuple[Framework, ...] = (
    Framework(
        "slop-be-gone",
        "slop-be-gone",
        "Code hygiene: placeholders, markers, size, secrets, and AST rigor.",
        REPO_ROOT / "sbg_manifest.json",
        "https://github.com/spamApply1/slop-be-gone",
    ),
    Framework(
        "design-be-gone",
        "design-be-gone",
        "Design consistency: styling, headings, filename case, module surface.",
        REPO_ROOT / "frameworks" / "design-be-gone.json",
        "https://github.com/spamApply1/design-be-gone",
    ),
    Framework(
        "chaos-be-gone",
        "chaos-be-gone",
        "Workflow sanity: CI, hooks, gitignore, README, and workflow secrets.",
        REPO_ROOT / "frameworks" / "chaos-be-gone.json",
        "https://github.com/spamApply1/chaos-be-gone",
    ),
)

_BY_ID = {framework.fid: framework for framework in FRAMEWORKS}


def _framework(fid: str) -> Framework:
    framework = _BY_ID.get(fid)
    if framework is None:
        raise KeyError(f"unknown framework: {fid}")
    return framework


def read_manifest(fid: str) -> dict:
    return json.loads(_framework(fid).manifest.read_text(encoding="utf-8"))


def _write_manifest(fid: str, manifest: dict) -> None:
    path = _framework(fid).manifest
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _rule_config(rule: dict) -> dict:
    return {key: value for key, value in rule.items() if key not in _META_FIELDS}


def _rule_view(rule: dict) -> dict:
    return {
        "id": rule.get("id", rule.get("type", "rule")),
        "type": rule.get("type", ""),
        "enabled": bool(rule.get("enabled", True)),
        "severity": rule.get("severity", "error"),
        "description": rule.get("description", ""),
        "what": rule.get("what", ""),
        "why": rule.get("why", ""),
        "config": _rule_config(rule),
    }


def list_frameworks() -> list[dict]:
    out: list[dict] = []
    for framework in FRAMEWORKS:
        rules = read_manifest(framework.fid).get("rules", [])
        views = [_rule_view(rule) for rule in rules]
        out.append(
            {
                "id": framework.fid,
                "name": framework.name,
                "description": framework.description,
                "repo": framework.repo,
                "rule_count": len(views),
                "enabled_count": sum(1 for view in views if view["enabled"]),
                "rules": views,
            }
        )
    return out


def _coerce_change(key: str, value: object) -> object:
    if key == "enabled":
        return bool(value)
    if key == "severity":
        text = str(value)
        if text not in _SEVERITIES:
            raise ValueError(f"severity must be one of {sorted(_SEVERITIES)}")
        return text
    if key in _NUMERIC_FIELDS:
        return int(value)
    raise ValueError(f"field {key!r} is not editable")


def update_rule(fid: str, rule_id: str, changes: dict) -> dict:
    """Apply validated *changes* to one rule and persist the manifest."""

    manifest = read_manifest(fid)
    for rule in manifest.get("rules", []):
        if rule.get("id", rule.get("type")) != rule_id:
            continue
        for key, value in changes.items():
            rule[key] = _coerce_change(key, value)
        _write_manifest(fid, manifest)
        return _rule_view(rule)
    raise KeyError(f"unknown rule {rule_id!r} in {fid}")
