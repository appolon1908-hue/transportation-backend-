from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Header, HTTPException, Request, status
from jwt import PyJWKClient

from app.config import get_settings


@dataclass(frozen=True)
class Actor:
    subject: str
    tenant_id: UUID
    permissions: frozenset[str]
    roles: frozenset[str]

    def require(self, permission: str) -> None:
        if permission not in self.permissions and "admin" not in self.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "FORBIDDEN", "message": "Permission denied."})


_jwks_clients: dict[str, PyJWKClient] = {}


def _jwks_client(issuer: str) -> PyJWKClient:
    client = _jwks_clients.get(issuer)
    if client is None:
        client = PyJWKClient(f"{issuer.rstrip('/')}/protocol/openid-connect/certs")
        _jwks_clients[issuer] = client
    return client


async def get_actor(
    request: Request,
    authorization: str | None = Header(default=None),
    x_dev_tenant_id: str | None = Header(default=None),
    x_dev_actor: str | None = Header(default=None),
    x_dev_permissions: str | None = Header(default=None),
) -> Actor:
    settings = get_settings()

    if settings.environment.lower() == "development" and not authorization:
        if not x_dev_tenant_id:
            raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED", "message": "Development tenant header is required."})
        try:
            tenant_id = UUID(x_dev_tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail={"code": "INVALID_TENANT", "message": "Invalid development tenant."}) from exc
        permissions = frozenset(p.strip() for p in (x_dev_permissions or "*").split(",") if p.strip())
        actor = Actor(x_dev_actor or "developer", tenant_id, permissions, frozenset({"admin"}) if "*" in permissions else frozenset())
        request.state.actor = actor
        return actor

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED", "message": "Bearer token is required."})
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise HTTPException(status_code=503, detail={"code": "IDENTITY_NOT_CONFIGURED", "message": "OIDC is not configured."})

    token = authorization.removeprefix("Bearer ").strip()
    try:
        signing_key = _jwks_client(settings.oidc_issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[a.strip() for a in settings.oidc_algorithms.split(",") if a.strip()],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
        tenant_raw = claims.get("tenant_id")
        if not tenant_raw:
            raise ValueError("tenant_id claim missing")
        tenant_id = UUID(str(tenant_raw))
        permissions_claim = claims.get("permissions", [])
        permissions = frozenset(permissions_claim if isinstance(permissions_claim, list) else str(permissions_claim).split())
        realm_access = claims.get("realm_access") or {}
        roles = frozenset(realm_access.get("roles", []))
        actor = Actor(str(claims["sub"]), tenant_id, permissions, roles)
        request.state.actor = actor
        return actor
    except Exception as exc:
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Token validation failed."}) from exc
