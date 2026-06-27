"""Open-Meteo geocoding adapter (real, keyless).

Free, no-API-key city geocoding — replaces Amadeus city lookup. Returns lat/long;
note it does not provide an IATA city code (used only for coordinates).
"""

from __future__ import annotations

import httpx

from wanderbot.domain import GeoPoint
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_BASE = "https://geocoding-api.open-meteo.com/v1/search"


class OpenMeteoGeoProvider:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def geocode_city(self, keyword: str) -> GeoPoint | None:
        resp = await self._http().get(
            _BASE, params={"name": keyword, "count": 1, "language": "en", "format": "json"}
        )
        if resp.status_code >= 400:
            log.warning("openmeteo_geocode_error", status=resp.status_code)
            return None
        results = resp.json().get("results") or []
        if not results:
            return None
        r = results[0]
        return GeoPoint(
            name=r.get("name", keyword),
            latitude=float(r.get("latitude", 0.0)),
            longitude=float(r.get("longitude", 0.0)),
            iata_city_code=None,
        )

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
