"""Tenant management API (admin only)."""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.jwt import User
from app.db.models import Tenant
from app.db.session import get_session
from app.tenancy import require_admin, resolve_tenant_id

router = APIRouter()

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class TenantCreate(BaseModel):
    """Payload for creating a tenant."""

    slug: str = Field(
        ...,
        pattern=_SLUG_RE.pattern,
        description="URL-safe tenant id, e.g. acme-corp",
    )
    name: str = Field(..., min_length=1, max_length=255)
    max_requests_per_minute: int = 0
    max_analyses_per_day: int = 0


class TenantOut(BaseModel):
    """Tenant representation."""

    id: int
    slug: str
    name: str
    active: bool
    max_requests_per_minute: int
    max_analyses_per_day: int


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    admin: User = Depends(require_admin),
) -> TenantOut:
    """Create a new tenant (admin only)."""
    if not _SLUG_RE.match(payload.slug):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="slug must be lowercase alphanumeric with dashes (3-64 chars)",
        )
    if payload.slug == "default":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="'default' is reserved for single-tenant mode",
        )

    async with get_session() as session:
        existing = await session.execute(select(Tenant).where(Tenant.slug == payload.slug))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"tenant '{payload.slug}' already exists",
            )

        tenant = Tenant(
            slug=payload.slug,
            name=payload.name,
            max_requests_per_minute=payload.max_requests_per_minute,
            max_analyses_per_day=payload.max_analyses_per_day,
        )
        session.add(tenant)
        await session.flush()
        return TenantOut(
            id=tenant.id,
            slug=tenant.slug,
            name=tenant.name,
            active=tenant.active,
            max_requests_per_minute=tenant.max_requests_per_minute,
            max_analyses_per_day=tenant.max_analyses_per_day,
        )


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(admin: User = Depends(require_admin)) -> list[TenantOut]:
    """List all tenants (admin only)."""
    async with get_session() as session:
        result = await session.execute(select(Tenant).order_by(Tenant.id))
        return [
            TenantOut(
                id=t.id,
                slug=t.slug,
                name=t.name,
                active=t.active,
                max_requests_per_minute=t.max_requests_per_minute,
                max_analyses_per_day=t.max_analyses_per_day,
            )
            for t in result.scalars().all()
        ]


@router.delete("/tenants/{slug}", response_model=TenantOut)
async def disable_tenant(slug: str, admin: User = Depends(require_admin)) -> TenantOut:
    """Disable a tenant (admin only). Data is retained, access is revoked."""
    if slug == "default":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot disable the default tenant",
        )

    async with get_session() as session:
        result = await session.execute(select(Tenant).where(Tenant.slug == slug))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"tenant '{slug}' not found",
            )
        tenant.active = False
        await session.flush()
        return TenantOut(
            id=tenant.id,
            slug=tenant.slug,
            name=tenant.name,
            active=tenant.active,
            max_requests_per_minute=tenant.max_requests_per_minute,
            max_analyses_per_day=tenant.max_analyses_per_day,
        )


@router.get("/tenants/current")
async def current_tenant(user: User = Depends(require_admin)) -> dict:
    """Show the tenant resolved for the current request."""
    tenant_id = resolve_tenant_id(user)
    return {"tenant_id": tenant_id, "user": user.username, "roles": user.roles}
