"""JWT authentication + scope-based authorization.

Authorization is enforced by code, never by the LLM. Every request carries a
verified ``user_id`` and scopes; consequential operations require an explicit
scope.
"""

from __future__ import annotations

import hashlib
import time

import jwt
from pydantic import BaseModel

from wanderbot.config import Settings, get_settings


def _signing_key(settings: Settings) -> bytes:
    """Derive a 32-byte HMAC key from the configured secret.

    PyJWT warns (and crypto best practice requires) that HS256 keys be at least
    32 bytes. We hash the configured secret so any value — even a short dev
    default — yields a full-strength key. Encode and decode use the same
    derivation, so tokens stay valid across a process.
    """
    return hashlib.sha256(settings.jwt_secret.get_secret_value().encode()).digest()


class Principal(BaseModel):
    user_id: str
    scopes: list[str] = []
    email: str | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def create_access_token(
    user_id: str,
    scopes: list[str] | None = None,
    *,
    email: str | None = None,
    settings: Settings | None = None,
    ttl_seconds: int = 7 * 24 * 3600,
) -> str:
    settings = settings or get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "scopes": scopes or [],
        "email": email,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(
        payload,
        _signing_key(settings),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, *, settings: Settings | None = None) -> Principal:
    settings = settings or get_settings()
    payload = jwt.decode(
        token,
        _signing_key(settings),
        algorithms=[settings.jwt_algorithm],
    )
    return Principal(
        user_id=payload["sub"], scopes=payload.get("scopes", []), email=payload.get("email")
    )


class AuthError(Exception):
    pass


def require_scope(principal: Principal, scope: str) -> None:
    if not principal.has_scope(scope):
        raise AuthError(f"missing required scope: {scope}")
