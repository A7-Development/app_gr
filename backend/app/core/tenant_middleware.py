"""Multi-tenant request context.

Extracts authenticated user + tenant from JWT and injects into request.
Every domain query must be scoped by this tenant_id.
"""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import InvalidTokenError, decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class RequestPrincipal:
    """Authenticated principal for a request."""

    user_id: UUID
    tenant_id: UUID
    email: str


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> RequestPrincipal:
    """Resolve the authenticated principal from the Authorization header.

    Raises 401 if missing, malformed or expired.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais nao fornecidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalido: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    try:
        principal = RequestPrincipal(
            user_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            email=payload["email"],
        )
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token com payload invalido",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    # Attach for downstream use (logging, audit, etc.)
    request.state.principal = principal
    return principal


async def get_current_tenant_id(
    principal: RequestPrincipal = Depends(get_current_principal),
) -> UUID:
    """Shortcut dependency returning only the tenant_id."""
    return principal.tenant_id
