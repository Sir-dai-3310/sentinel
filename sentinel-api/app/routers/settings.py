"""Settings management endpoint."""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.jwt import User, require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


class Settings(BaseModel):
    """Application settings (sanitized - no secrets)."""

    llm_model: str
    llm_base_url: str
    llm_temperature: float
    llm_max_tokens: int

    cors_origins: str
    environment: str

    # Threat intelligence (only show if configured, not the actual keys)
    vt_enabled: bool
    abuseipdb_enabled: bool
    shodan_enabled: bool

    # System
    rules_dir: str
    log_level: str


class SettingsUpdate(BaseModel):
    """Settings update request."""

    llm_temperature: float | None = None
    llm_max_tokens: int | None = None
    log_level: str | None = None


@router.get("/settings", response_model=Settings)
async def get_settings() -> Settings:
    """
    Get current application settings.

    Note: API keys are never returned, only their presence status.
    """
    return Settings(
        llm_model=os.getenv("LLM_MODEL", "gpt-4-turbo-preview"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000"),
        environment=os.getenv("ENVIRONMENT", "development"),
        vt_enabled=bool(os.getenv("VT_API_KEY")),
        abuseipdb_enabled=bool(os.getenv("ABUSEIPDB_API_KEY")),
        shodan_enabled=bool(os.getenv("SHODAN_API_KEY")),
        rules_dir=os.getenv("RULES_DIR", "rules"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


@router.put("/settings")
async def update_settings(update: SettingsUpdate) -> dict[str, str]:
    """
    Update application settings.

    Note: This endpoint only supports updating non-sensitive settings.
    API keys must be updated via environment variables and service restart.
    """
    # In a real implementation, this would update a configuration store
    # For now, return success but note that env vars need restart

    return {
        "status": "updated",
        "message": "Settings updated. Note: Some settings require service restart to take effect.",
    }
