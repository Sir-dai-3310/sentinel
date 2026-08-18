"""Multi-tenancy support for Sentinel API.

Single-tenant mode (default): every request resolves to the "default"
tenant and no Tenant row is required.

Multi-tenant mode (MULTI_TENANT_ENABLED=true): the tenant slug from the
JWT `tenant` claim is validated against the tenants table and every
tenant-scoped query must apply `tenant_filter`.
"""

import os
from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import Select

from app.auth.jwt import User, get_current_user

DEFAULT_TENANT = "default"


def multi_tenant_enabled() -> bool:
    """Whether multi-tenant mode is active."""
    return os.getenv("MULTI_TENANT_ENABLED", "false").lower() == "true"


def resolve_tenant_id(user: User) -> str:
    """
    Resolve the tenant for a request.

    Single-tenant mode collapses everything to DEFAULT_TENANT so legacy
    tokens and data keep working; multi-tenant mode trusts the JWT claim
    (validated at token issuance time).
    """
    if not multi_tenant_enabled():
        return DEFAULT_TENANT
    return user.tenant_id or DEFAULT_TENANT


def tenant_filter(stmt: Select, model: Any, tenant_id: str) -> Select:
    """
    Apply tenant isolation to a SQLAlchemy select.

    Usage:
        stmt = tenant_filter(select(AnalysisResult), AnalysisResult, tenant_id)
    """
    return stmt.where(model.tenant_id == tenant_id)


async def get_tenant_context(user: User = Depends(get_current_user)) -> str:
    """FastAPI dependency: resolved tenant id for the current request."""
    return resolve_tenant_id(user)


def require_admin(user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency: require the admin role."""
    if "admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user
