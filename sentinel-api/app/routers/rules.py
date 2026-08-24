"""Rules management endpoints with full CRUD."""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.jwt import User, require_auth
from app.rbac import require_permission

# Read access for all authenticated users; write access is admin-only
# (the RBAC matrix existed but was never mounted before).
router = APIRouter(dependencies=[Depends(require_auth)])

RULES_DIR = Path(os.getenv("RULES_DIR", "rules"))

# Rule IDs become filenames — restrict to safe characters (covers Sigma UUIDs and R### style).
RULE_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


def _iter_rule_files() -> list[Path]:
    """All ``*.yml`` rule files under RULES_DIR (empty when dir missing)."""
    if not RULES_DIR.exists():
        return []
    return list(RULES_DIR.rglob("*.yml"))


def _load_rule_file(path: Path) -> dict[str, Any] | None:
    """Parse one rule file; malformed files are skipped (None)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _find_rule_file_by_id(rule_id: str) -> Path | None:
    """Locate the file whose parsed ``id`` equals ``rule_id``."""
    for yml_file in _iter_rule_files():
        data = _load_rule_file(yml_file)
        if data is not None and data.get("id") == rule_id:
            return yml_file
    return None


class Rule(BaseModel):
    """Sigma rule."""

    id: str = Field(pattern=RULE_ID_PATTERN)
    title: str
    description: str | None = None
    level: str = "medium"
    status: str = "stable"
    author: str | None = None
    logsource: dict[str, Any]
    detection: dict[str, Any]
    tags: list[str] = []
    falsepositives: list[str] = []


class RuleSummary(BaseModel):
    """Rule summary for listing."""

    id: str
    title: str
    level: str
    file_path: str


@router.get("/rules")
async def list_rules() -> dict[str, Any]:
    """List all Sigma rules."""
    rules = []

    for yml_file in _iter_rule_files():
        data = _load_rule_file(yml_file)
        if data is None:
            print(f"Failed to load rule {yml_file}")
            continue
        rules.append(
            RuleSummary(
                id=data.get("id", "unknown"),
                title=data.get("title", "Untitled"),
                level=data.get("level", "medium"),
                file_path=str(yml_file.relative_to(RULES_DIR)),
            )
        )

    return {"total": len(rules), "rules": rules}


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str) -> Rule:
    """Get a specific rule by ID."""
    if not RULES_DIR.exists():
        raise HTTPException(status_code=404, detail="Rules directory not found")

    rule_file = _find_rule_file_by_id(rule_id)
    if rule_file is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    data = _load_rule_file(rule_file)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return Rule(**data)


@router.post("/rules", dependencies=[Depends(require_permission("rule_create"))])
async def create_rule(rule: Rule) -> dict[str, str]:
    """Create a new Sigma rule."""
    if not RULES_DIR.exists():
        RULES_DIR.mkdir(parents=True)

    # Check if rule ID already exists
    try:
        existing = await get_rule(rule.id)
        raise HTTPException(status_code=409, detail=f"Rule {rule.id} already exists")
    except HTTPException as e:
        if e.status_code != 404:
            raise

    # Determine category from tags
    category = "custom"
    if rule.tags:
        for tag in rule.tags:
            if tag.startswith("attack."):
                tactic = tag.split(".")[1] if len(tag.split(".")) > 1 else "custom"
                # Sanitize: category becomes a directory name under RULES_DIR.
                category = re.sub(r"[^A-Za-z0-9_-]", "", tactic) or "custom"
                break

    # Create rule file
    category_dir = RULES_DIR / category
    category_dir.mkdir(exist_ok=True)

    filename = f"{rule.id.lower().replace(' ', '_')}.yml"
    file_path = category_dir / filename

    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(rule.model_dump(exclude_none=True), f, default_flow_style=False)

    return {"status": "created", "file_path": str(file_path.relative_to(RULES_DIR))}


@router.put("/rules/{rule_id}", dependencies=[Depends(require_permission("rule_update"))])
async def update_rule(rule_id: str, rule: Rule) -> dict[str, str]:
    """Update an existing rule."""
    existing_file = _find_rule_file_by_id(rule_id)
    if not existing_file:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    # Update rule file
    with open(existing_file, "w", encoding="utf-8") as f:
        yaml.dump(rule.model_dump(exclude_none=True), f, default_flow_style=False)

    return {"status": "updated", "file_path": str(existing_file.relative_to(RULES_DIR))}


@router.delete("/rules/{rule_id}", dependencies=[Depends(require_permission("rule_delete"))])
async def delete_rule(rule_id: str) -> dict[str, str]:
    """Delete a rule."""
    existing_file = _find_rule_file_by_id(rule_id)
    if not existing_file:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    # Delete file
    existing_file.unlink()

    return {"status": "deleted", "rule_id": rule_id}


@router.post("/rules/reload", dependencies=[Depends(require_permission("rule_reload"))])
async def reload_rules() -> dict[str, Any]:
    """Reload all rules (trigger engine reload)."""
    # In a real implementation, this would trigger the Rust engine to reload rules
    # For now, just return the count
    count = 0
    if RULES_DIR.exists():
        count = len(list(RULES_DIR.rglob("*.yml")))

    return {"status": "reloaded", "count": count}
