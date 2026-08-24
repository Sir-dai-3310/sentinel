"""Authentication endpoints: JWT login.

User accounts are configured via environment variables (no user DB yet):

- ``SENTINEL_USERS``: JSON mapping of username to
  ``{"password": ..., "roles": [...], "tenant": "..."}``. Highest priority.
The ``admin``/``admin`` bootstrap default is only tolerated in explicitly
local environments (see ``app.env.is_local_mode``); anywhere else the router
refuses to issue tokens for it.
"""

import hmac
import json
import os
import warnings
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.jwt import Token, create_access_token
from app.env import is_local_mode
from app.security import AuditLogger

router = APIRouter()

DEFAULT_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

audit_logger = AuditLogger()


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
    if DEFAULT_ADMIN_PASSWORD == "admin" and is_local_mode():
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
async def login(credentials: LoginRequest, request: Request) -> Token:
    """
    Exchange username/password for a JWT access token.

    Returns a bearer token used for all subsequent authenticated requests.
    """
    user = _load_users().get(credentials.username)
    stored_password = str(user.get("password", "")) if user else ""
    # Constant-time compare on BOTH paths (unknown user vs wrong password) to
    # avoid user enumeration / timing side channels.
    password_ok = hmac.compare_digest(stored_password, credentials.password)
    client_ip = request.client.host if request.client else ""

    if user is None or not password_ok:
        audit_logger.log(
            action="login",
            user=credentials.username,
            success=False,
            ip=client_ip,
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fail-closed: the admin/admin bootstrap default never issues tokens
    # outside explicitly local environments.
    if (
        credentials.username == DEFAULT_ADMIN_USERNAME
        and DEFAULT_ADMIN_PASSWORD == "admin"
        and not is_local_mode()
    ):
        audit_logger.log(
            action="login",
            user=credentials.username,
            success=False,
            ip=client_ip,
            details={"reason": "default_credentials_blocked"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Default admin credentials are disabled; set ADMIN_PASSWORD or SENTINEL_USERS",
        )

    token = create_access_token(
        subject=credentials.username,
        tenant_id=user.get("tenant", "default"),
        roles=user.get("roles", []),
    )
    audit_logger.log(
        action="login",
        user=credentials.username,
        success=True,
        ip=client_ip,
        details={"tenant": user.get("tenant", "default")},
    )
    return Token(access_token=token)
