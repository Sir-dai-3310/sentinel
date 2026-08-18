"""Authentication endpoints: JWT login.

User accounts are configured via environment variables (no user DB yet):

- ``SENTINEL_USERS``: JSON mapping of username to
  ``{"password": ..., "roles": [...], "tenant": "..."}``. Highest priority.
- ``ADMIN_USERNAME`` / ``ADMIN_PASSWORD``: single bootstrap account
  (defaults ``admin`` / ``admin`` for local dev, with admin role).
"""

import json
import os
import warnings
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth.jwt import Token, create_access_token

router = APIRouter()

DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")


class LoginRequest(BaseModel):
    """Login credentials."""

    username: str
    password: str


def _load_users() -> dict[str, dict[str, Any]]:
    """Load configured users from env (SENTINEL_USERS JSON or admin fallback)."""
    raw = os.getenv("SENTINEL_USERS")
    if raw:
        try:
            users = json.loads(raw)
            if isinstance(users, dict):
                return users
        except (json.JSONDecodeError, TypeError):
            warnings.warn("SENTINEL_USERS is not valid JSON; falling back to default admin account")
    if DEFAULT_ADMIN_PASSWORD == "admin":
        warnings.warn(
            "Using default admin/admin credentials — set ADMIN_PASSWORD or SENTINEL_USERS before exposing the API",
            stacklevel=2,
        )
    return {
        DEFAULT_ADMIN_USERNAME: {
            "password": DEFAULT_ADMIN_PASSWORD,
            "roles": ["admin"],
            "tenant": "default",
        }
    }


@router.post("/auth/login", response_model=Token)
async def login(credentials: LoginRequest) -> Token:
    """
    Exchange username/password for a JWT access token.

    Returns a bearer token used for all subsequent authenticated requests.
    """
    user = _load_users().get(credentials.username)
    if user is None or user.get("password") != credentials.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        subject=credentials.username,
        tenant_id=user.get("tenant", "default"),
        roles=user.get("roles", []),
    )
    return Token(access_token=token)
