"""Rules management endpoints with full CRUD."""

import os
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.jwt import User, require_auth

router = APIRouter(dependencies=[Depends(require_auth)])

RULES_DIR = Path(os.getenv("RULES_DIR", "rules"))

# Rule IDs become filenames — restrict to safe characters (covers Sigma UUIDs and R### style).
RULE_ID_PATTERN = r"^[A-Za-z0-9_-]+$"


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

    if not RULES_DIR.exists():
        return {"total": 0, "rules": []}

    for yml_file in RULES_DIR.rglob("*.yml"):
        try:
            with open(yml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                rules.append(
                    RuleSummary(
                        id=data.get("id", "unknown"),
                        title=data.get("title", "Untitled"),
                        level=data.get("level", "medium"),
                        file_path=str(yml_file.relative_to(RULES_DIR)),
                    )
                )
        except Exception as e:
            print(f"Failed to load rule {yml_file}: {e}")

    return {"total": len(rules), "rules": rules}


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str) -> Rule:
    """Get a specific rule by ID."""
    if not RULES_DIR.exists():
        raise HTTPException(status_code=404, detail="Rules directory not found")

    for yml_file in RULES_DIR.rglob("*.yml"):
        try:
            with open(yml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data.get("id") == rule_id:
                    return Rule(**data)
        except Exception:
            continue

    raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")


@router.post("/rules")
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


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, rule: Rule) -> dict[str, str]:
    """Update an existing rule."""
    # Find existing rule file
    existing_file = None
    for yml_file in RULES_DIR.rglob("*.yml"):
        try:
            with open(yml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data.get("id") == rule_id:
                    existing_file = yml_file
                    break
        except Exception:
            continue

    if not existing_file:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    # Update rule file
    with open(existing_file, "w", encoding="utf-8") as f:
        yaml.dump(rule.model_dump(exclude_none=True), f, default_flow_style=False)

    return {"status": "updated", "file_path": str(existing_file.relative_to(RULES_DIR))}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str) -> dict[str, str]:
    """Delete a rule."""
    # Find existing rule file
    existing_file = None
    for yml_file in RULES_DIR.rglob("*.yml"):
        try:
            with open(yml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data.get("id") == rule_id:
                    existing_file = yml_file
                    break
        except Exception:
            continue

    if not existing_file:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    # Delete file
    existing_file.unlink()

    return {"status": "deleted", "rule_id": rule_id}


@router.post("/rules/reload")
async def reload_rules() -> dict[str, Any]:
    """Reload all rules (trigger engine reload)."""
    # In a real implementation, this would trigger the Rust engine to reload rules
    # For now, just return the count
    count = 0
    if RULES_DIR.exists():
        count = len(list(RULES_DIR.rglob("*.yml")))

    return {"status": "reloaded", "count": count}
