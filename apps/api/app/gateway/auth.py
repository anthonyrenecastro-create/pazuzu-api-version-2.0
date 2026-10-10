"""Mock OAuth2/OIDC for dev + real JWT path via python-jose.

Config:
  PAZUZU_MOCK_AUTH=true (default): accepts ANY Bearer token, maps it to a
      deterministic dev principal with full dev scopes. NO credentials are
      invented or stored; the token is never validated, only hashed for an id.
      Dev-only: do not enable in production.
  Real path (PAZUZU_MOCK_AUTH=false): validates RS256 JWTs against the JWKS at
  PAZUZU_OIDC_JWKS_URL, issuer PAZUZU_OIDC_ISSUER, audience PAZUZU_OIDC_AUDIENCE.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def _mock_auth_enabled() -> bool:
    return os.environ.get("PAZUZU_MOCK_AUTH", "true").strip().lower() in ("1", "true", "yes")


@dataclass
class Principal:
    sub: str
    scopes: list[str] = field(default_factory=list)
    tenant_id: str = "dev"


def _mock_principal(credentials: HTTPAuthorizationCredentials | None) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token (mock auth is enabled; any Bearer token is accepted)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    digest = hashlib.sha256(token.encode()).hexdigest()[:12]
    # Dev-only: any token maps to a principal with full dev scopes. The token
    # itself is the credential; nothing is invented or persisted.
    return Principal(
        sub=f"dev-user:{digest}",
        scopes=["v2:read", "v2:write", "admin"],
        tenant_id="dev",
    )


_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    url = os.environ.get("PAZUZU_OIDC_JWKS_URL", "").strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PAZUZU_OIDC_JWKS_URL is not configured for real auth",
        )
    resp = httpx.get(url, timeout=10.0)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    return _jwks_cache


def _real_principal(credentials: HTTPAuthorizationCredentials | None) -> Principal:
    from jose import jwt

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    issuer = os.environ.get("PAZUZU_OIDC_ISSUER", "").strip()
    audience = os.environ.get("PAZUZU_OIDC_AUDIENCE", "").strip()
    jwks = _get_jwks()  # raises 500 HTTPException itself when unconfigured
    try:
        claims = jwt.decode(
            credentials.credentials,
            jwks,
            algorithms=["RS256"],
            issuer=issuer or None,
            audience=audience or None,
            options={"verify_aud": bool(audience)},
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {type(exc).__name__}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    scope_claim = claims.get("scope", "")
    scopes = scope_claim.split() if isinstance(scope_claim, str) else list(scope_claim or [])
    return Principal(
        sub=str(claims.get("sub", "unknown")),
        scopes=scopes,
        tenant_id=str(claims.get("tenant") or claims.get("org") or "default"),
    )


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if _mock_auth_enabled():
        return _mock_principal(credentials)
    return _real_principal(credentials)


def require_scopes(*needed: str):
    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        missing = [s for s in needed if s not in principal.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {missing}",
            )
        return principal

    return _dep


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if "admin" not in principal.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin scope required",
        )
    return principal
