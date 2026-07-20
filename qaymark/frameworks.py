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
    domain: str
    scope: str


FRAMEWORKS: tuple[Framework, ...] = (
    Framework(
        "slop-be-gone",
        "slop-be-gone",
        "Code hygiene: placeholders, markers, size, secrets, and AST rigor.",
        REPO_ROOT / "sbg_manifest.json",
        "https://github.com/spamApply1/slop-be-gone",
        "hygiene",
        "single-file",
    ),
    Framework(
        "design-be-gone",
        "design-be-gone",
        "Design consistency: styling, headings, filename case, module surface.",
        REPO_ROOT / "frameworks" / "design-be-gone.json",
        "https://github.com/spamApply1/design-be-gone",
        "design",
        "ui-markup",
    ),
    Framework(
        "chaos-be-gone",
        "chaos-be-gone",
        "Workflow sanity: CI, hooks, gitignore, README, and workflow secrets.",
        REPO_ROOT / "frameworks" / "chaos-be-gone.json",
        "https://github.com/spamApply1/chaos-be-gone",
        "workflow",
        "repo-structure",
    ),
    Framework(
        "drift-be-gone",
        "drift-be-gone",
        "Architecture: cycles, layering, forbidden deps, orphans, and the map.",
        REPO_ROOT / "frameworks" / "drift-be-gone.json",
        "https://github.com/spamApply1/drift-be-gone",
        "architecture",
        "cross-module",
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
                "domain": framework.domain,
                "scope": framework.scope,
                "rule_count": len(views),
                "enabled_count": sum(1 for view in views if view["enabled"]),
                "rules": views,
            }
        )
    return out


def check_overlap() -> list[str]:
    """Assert the cluster's frameworks stay in their lanes.

    Vibing governance: two frameworks must never define the same rule id, claim
    the same domain, or claim the same scope. slop-be-gone owns single-file
    hygiene; drift-be-gone owns cross-module architecture; they must not blur.
    """

    problems: list[str] = []
    rule_owner: dict[str, str] = {}
    domain_owner: dict[str, str] = {}
    scope_owner: dict[str, str] = {}
    for framework in FRAMEWORKS:
        _claim(domain_owner, framework.domain, framework.fid, "domain", problems)
        _claim(scope_owner, framework.scope, framework.fid, "scope", problems)
        manifest = json.loads(framework.manifest.read_text(encoding="utf-8"))
        for rule in manifest.get("rules", []):
            rid = rule.get("id", rule.get("type", ""))
            _claim(rule_owner, rid, framework.fid, "rule id", problems)
    return problems


def _claim(owner: dict[str, str], key: str, fid: str, label: str, problems: list[str]) -> None:
    if key in owner and owner[key] != fid:
        problems.append(f"{label} '{key}' claimed by both {owner[key]} and {fid}")
    else:
        owner[key] = fid


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


def validate_manifest(manifest: object) -> list[str]:
    """Structural checks so a raw edit can't save broken policy."""

    problems: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    rules = manifest.get("rules")
    if not isinstance(rules, list):
        return ["manifest must contain a 'rules' array"]
    seen: set[str] = set()
    for index, rule in enumerate(rules):
        label = f"rule {index + 1}"
        if not isinstance(rule, dict):
            problems.append(f"{label} is not an object")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            problems.append(f"{label} is missing a non-empty 'id'")
        elif rule_id in seen:
            problems.append(f"rule '{rule_id}' has a duplicate id")
        else:
            seen.add(rule_id)
        if not isinstance(rule.get("type"), str) or not rule.get("type", "").strip():
            problems.append(f"{label} is missing a non-empty 'type'")
    return problems


def raw_manifest(fid: str) -> str:
    """The framework's manifest as pretty JSON for a full-text editor."""

    return json.dumps(read_manifest(fid), indent=2) + "\n"


def replace_manifest(fid: str, manifest: dict) -> dict:
    """Replace a framework's entire manifest after structural validation."""

    problems = validate_manifest(manifest)
    if problems:
        raise ValueError("; ".join(problems))
    _write_manifest(fid, manifest)
    return {"rules": len(manifest.get("rules", []))}


def add_rule(fid: str, rule: dict) -> dict:
    """Append a new rule; the manifest must stay valid afterwards."""

    if not isinstance(rule, dict):
        raise ValueError("rule must be a JSON object")
    manifest = read_manifest(fid)
    manifest.setdefault("rules", []).append(rule)
    problems = validate_manifest(manifest)
    if problems:
        raise ValueError("; ".join(problems))
    _write_manifest(fid, manifest)
    return _rule_view(rule)


def delete_rule(fid: str, rule_id: str) -> dict:
    """Remove a rule by id and persist the manifest."""

    manifest = read_manifest(fid)
    rules = manifest.get("rules", [])
    kept = [rule for rule in rules if rule.get("id", rule.get("type")) != rule_id]
    if len(kept) == len(rules):
        raise KeyError(f"unknown rule {rule_id!r} in {fid}")
    manifest["rules"] = kept
    _write_manifest(fid, manifest)
    return {"deleted": rule_id, "rules": len(kept)}
