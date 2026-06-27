"""Shared Amadeus HTTP helper (auth + GET with retry)."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger
from wanderbot.providers.amadeus.token_manager import AmadeusTokenManager
from wanderbot.providers.base import ProviderError

log = get_logger(__name__)


class AmadeusBase:
    def __init__(
        self,
        settings: Settings | None = None,
        token_manager: AmadeusTokenManager | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self._settings = settings or get_settings()
        self._tokens = token_manager or AmadeusTokenManager(self._settings, client)
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        reraise=True,
    )
    async def _get(self, path: str, params: dict[str, Any]) -> dict:
        token = await self._tokens.get_token()
        resp = await self._http().get(
            f"{self._settings.amadeus_base_url}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            log.warning("amadeus_error", path=path, status=resp.status_code, body=resp.text[:200])
            if resp.status_code == 429:
                raise ProviderError("amadeus_rate_limited")
            raise ProviderError(f"amadeus {path} failed ({resp.status_code})")
        return resp.json()  # type: ignore[no-any-return]

    async def aclose(self) -> None:
        await self._tokens.aclose()
        if self._owns_client and self._client is not None:
            await self._client.aclose()
