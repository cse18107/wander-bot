"""Amadeus OAuth2 (client-credentials) token manager.

Amadeus access tokens are short-lived. This caches the token and refreshes it
only when it's near expiry, behind an async lock so concurrent callers don't
stampede the auth endpoint.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_EXPIRY_SKEW_SECONDS = 30


class AmadeusTokenManager:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def get_token(self) -> str:
        if self._token and time.monotonic() < self._expires_at - _EXPIRY_SKEW_SECONDS:
            return self._token

        async with self._lock:
            # Double-check after acquiring the lock.
            if self._token and time.monotonic() < self._expires_at - _EXPIRY_SKEW_SECONDS:
                return self._token
            return await self._fetch_token()

    async def _fetch_token(self) -> str:
        s = self._settings
        if s.amadeus_client_id is None or s.amadeus_client_secret is None:
            raise RuntimeError("Amadeus credentials missing (WB_AMADEUS_CLIENT_ID/SECRET)")

        resp = await self._http().post(
            f"{s.amadeus_base_url}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": s.amadeus_client_id.get_secret_value(),
                "client_secret": s.amadeus_client_secret.get_secret_value(),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = str(payload["access_token"])
        self._expires_at = time.monotonic() + float(payload.get("expires_in", 1799))
        log.info("amadeus_token_refreshed", expires_in=payload.get("expires_in"))
        return self._token

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
