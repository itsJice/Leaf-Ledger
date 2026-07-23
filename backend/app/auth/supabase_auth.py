"""Supabase Auth for Leaf & Ledger.

Self-contained JWT verification with no Databutton coupling. Supabase signs
access tokens either with modern asymmetric keys (verified against the project's
public JWKS endpoint) or with the legacy shared HS256 secret, so both are
supported — JWKS first, secret as a fallback.

Usage in a router:

    from app.auth.supabase_auth import CurrentUser

    @router.get("/thing")
    async def read_thing(user: CurrentUser):
        ...  # user.sub is the verified Supabase user id
"""

from __future__ import annotations

import functools
import os
from typing import Annotated, Any, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient
from pydantic import BaseModel

# Supabase always issues access tokens with this audience for signed-in users.
SUPABASE_AUDIENCE = "authenticated"


class AuthUser(BaseModel):
    """A verified Supabase user."""

    sub: str
    email: Optional[str] = None
    role: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.email or self.sub


def supabase_url() -> str:
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    if not url:
        raise RuntimeError(
            "SUPABASE_URL is not set — cannot verify logins. "
            "Set it to https://<project-ref>.supabase.co"
        )
    return url


def jwks_url() -> str:
    return f"{supabase_url()}/auth/v1/.well-known/jwks.json"


def expected_issuer() -> str:
    return f"{supabase_url()}/auth/v1"


@functools.cache
def _jwks_client(url: str) -> PyJWKClient:
    # PyJWKClient caches the fetched keys, so this is one network call per key id.
    return PyJWKClient(url, cache_keys=True)


def _decode_with_jwks(token: str) -> Optional[dict[str, Any]]:
    try:
        signing_key = _jwks_client(jwks_url()).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            key=signing_key.key,
            algorithms=[signing_key.algorithm_name],
            audience=SUPABASE_AUDIENCE,
            issuer=expected_issuer(),
        )
    except Exception:
        return None


def _decode_with_secret(token: str) -> Optional[dict[str, Any]]:
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        return None
    try:
        return jwt.decode(
            token,
            key=secret,
            algorithms=["HS256"],
            audience=SUPABASE_AUDIENCE,
            issuer=expected_issuer(),
        )
    except Exception:
        return None


def verify_token(token: str) -> Optional[AuthUser]:
    """Verify a Supabase access token. Returns None if it isn't valid."""
    payload = _decode_with_jwks(token) or _decode_with_secret(token)
    if not payload:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    return AuthUser(sub=sub, email=payload.get("email"), role=payload.get("role"))


def bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization") or ""
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    return token or None


def get_current_user(request: Request) -> AuthUser:
    """FastAPI dependency: require a signed-in Supabase user."""
    token = bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = verify_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired — please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(request: Request) -> Optional[AuthUser]:
    """Like get_current_user but returns None instead of raising."""
    token = bearer_token(request)
    return verify_token(token) if token else None


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
OptionalUser = Annotated[Optional[AuthUser], Depends(get_optional_user)]
