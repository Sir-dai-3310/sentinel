"""JWT authentication for Sentinel API."""

import os
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.env import is_local_mode

# JWT Configuration — fail-closed: the default secret is only tolerated in
# explicitly local environments; anywhere else (staging/prod/typo'd values)
# the app refuses to start rather than accepting forgeable tokens.
SECRET_KEY = os.getenv("JWT_SECRET", "CHANGE_THIS_IN_PRODUCTION")
if not is_local_mode() and SECRET_KEY == "CHANGE_THIS_IN_PRODUCTION":
    raise ValueError(
        "JWT_SECRET must be set when ENVIRONMENT is not one of "
        "development/dev/local (default secret is insecure)"
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# Security scheme
security = HTTPBearer(auto_error=False)


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """JWT token payload."""

    sub: str  # subject (user id or service name)
    exp: datetime
    iat: datetime
    tenant: str = "default"
    roles: list[str] = []


class User(BaseModel):
    """Authenticated user."""

    username: str
    scopes: list[str] = []
    tenant_id: str = "default"
    roles: list[str] = []


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
    tenant_id: str | None = None,
    roles: list[str] | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        subject: Token subject (usually user ID or service name)
        expires_delta: Optional custom expiration time
        tenant_id: Tenant slug embedded as the `tenant` claim
        roles: Role names embedded as the `roles` claim

    Returns:
        Encoded JWT token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.utcnow(),
        "tenant": tenant_id or "default",
        "roles": roles or [],
    }

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token data

    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: str = payload.get("sub")
        exp = payload.get("exp")
        iat = payload.get("iat")

        if sub is None or exp is None or iat is None:
            raise credentials_exception

        token_data = TokenData(
            sub=sub,
            exp=datetime.fromtimestamp(exp),
            iat=datetime.fromtimestamp(iat),
            tenant=payload.get("tenant", "default"),
            roles=payload.get("roles", []),
        )
        return token_data

    except (JWTError, TypeError, ValueError):
        raise credentials_exception


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> User:
    """
    Get current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        Authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_token(credentials.credentials)
    return User(
        username=token_data.sub,
        scopes=[],
        tenant_id=token_data.tenant,
        roles=token_data.roles,
    )


def require_auth(user: User = Depends(get_current_user)) -> User:
    """
    Dependency to require authentication.

    Usage:
        @router.get("/protected", dependencies=[Depends(require_auth)])
        async def protected_endpoint():
            ...

    Or:
        @router.get("/protected")
        async def protected_endpoint(user: User = Depends(require_auth)):
            ...
    """
    return user


# Optional: API Key authentication (simpler alternative to JWT)
async def get_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> str:
    """
    Get API key from Bearer token.

    Simpler alternative to JWT for service-to-service authentication.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = credentials.credentials
    # Filter empties: an unset API_KEYS must not accept a blank bearer token.
    valid_keys = [k for k in os.getenv("API_KEYS", "").split(",") if k]

    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return api_key
