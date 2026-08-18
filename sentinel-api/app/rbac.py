"""RBAC (Role-Based Access Control) for Sentinel API."""

import os
from enum import Enum
from typing import Any

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.jwt import User, get_current_user


class Role(str, Enum):
    """User roles."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class RoleConfig:
    """Role-based permissions configuration."""

    # Define which roles can access which operations
    PERMISSIONS: dict[str, list[Role]] = {
        # Analysis operations
        "analyze": [Role.ADMIN, Role.ANALYST],
        "analyze_batch": [Role.ADMIN, Role.ANALYST],
        "view_results": [Role.ADMIN, Role.ANALYST, Role.VIEWER],

        # Rule management
        "rule_create": [Role.ADMIN],
        "rule_update": [Role.ADMIN],
        "rule_delete": [Role.ADMIN],
        "rule_list": [Role.ADMIN, Role.ANALYST, Role.VIEWER],
        "rule_view": [Role.ADMIN, Role.ANALYST, Role.VIEWER],
        "rule_reload": [Role.ADMIN],

        # Settings
        "settings_view": [Role.ADMIN, Role.ANALYST],
        "settings_update": [Role.ADMIN],

        # Statistics
        "stats_view": [Role.ADMIN, Role.ANALYST, Role.VIEWER],
    }

    @classmethod
    def has_permission(cls, operation: str, role: Role) -> bool:
        """Check if a role has permission for an operation."""
        allowed_roles = cls.PERMISSIONS.get(operation, [])
        return role in allowed_roles


class UserWithRole(User):
    """User with role information."""

    role: Role = Role.VIEWER


def get_user_role(user: User) -> Role:
    """
    Get user role from JWT claims or environment.

    In production, this would query a user database.
    For now, use environment variable mapping or JWT claims.
    """
    # Check if user has role in JWT (would be set by auth provider)
    # For demo purposes, use a simple mapping
    admin_users = os.getenv("ADMIN_USERS", "admin").split(",")
    analyst_users = os.getenv("ANALYST_USERS", "analyst").split(",")

    if user.username in admin_users:
        return Role.ADMIN
    elif user.username in analyst_users:
        return Role.ANALYST
    else:
        return Role.VIEWER


async def get_current_user_with_role(
    user: User = Depends(get_current_user),
) -> UserWithRole:
    """Get current user with role information."""
    role = get_user_role(user)
    return UserWithRole(username=user.username, scopes=user.scopes, role=role)


def require_permission(operation: str):
    """
    Dependency to require a specific permission.

    Usage:
        @router.post("/rules", dependencies=[Depends(require_permission("rule_create"))])
        async def create_rule():
            ...
    """

    async def permission_checker(
        user: UserWithRole = Depends(get_current_user_with_role),
    ) -> UserWithRole:
        if not RoleConfig.has_permission(operation, user.role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {operation}, Role: {user.role}",
            )
        return user

    return permission_checker


def require_role(required_role: Role):
    """
    Dependency to require a specific role.

    Usage:
        @router.delete("/rules/{id}", dependencies=[Depends(require_role(Role.ADMIN))])
        async def delete_rule():
            ...
    """

    async def role_checker(
        user: UserWithRole = Depends(get_current_user_with_role),
    ) -> UserWithRole:
        # Define role hierarchy
        role_hierarchy = {
            Role.ADMIN: [Role.ADMIN, Role.ANALYST, Role.VIEWER],
            Role.ANALYST: [Role.ANALYST, Role.VIEWER],
            Role.VIEWER: [Role.VIEWER],
        }

        if user.role not in role_hierarchy.get(required_role, []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient role. Required: {required_role}, Current: {user.role}",
            )
        return user

    return role_checker
