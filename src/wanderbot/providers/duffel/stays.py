"""Duffel Stays adapter (real) — hotels searched by coordinates.

Uses the same Duffel token as flights. Searches around a lat/long (from the
geocoder) rather than a city code, which fits the Open-Meteo geo step.
"""

from __future__ import annotations

from datetime import date

import httpx

from wanderbot.config import Settings, get_settings
from wanderbot.domain import HotelOffer, Money
from wanderbot.observability.logging import get_logger
from wanderbot.providers.base import ProviderError

log = get_logger(__name__)

_BASE = "https://api.duffel.com"
# Duffel sandbox test-hotel location (see docs: Test Hotels).
_TEST_HOTEL_COORDS = (-24.38, -128.32)


class DuffelStaysProvider:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self._settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=25.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        if self._settings.duffel_api_key is None:
            raise ProviderError("duffel_api_key_missing")
        return {
            "Authorization": f"Bearer {self._settings.duffel_api_key.get_secret_value()}",
            "Duffel-Version": self._settings.duffel_version,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def search_stays(
        self,
        lat: float,
        lon: float,
        check_in: date,
        check_out: date,
        adults: int = 1,
        *,
        max_results: int = 5,
    ) -> list[HotelOffer]:
        # In sandbox, test hotels only exist at a fixed coordinate.
        if self._settings.duffel_use_test_hotels:
            lat, lon = _TEST_HOTEL_COORDS
        body = {
            "data": {
                "rooms": 1,
                "check_in_date": check_in.isoformat(),
                "check_out_date": check_out.isoformat(),
                "guests": [{"type": "adult"} for _ in range(max(adults, 1))],
                "location": {
                    "radius": 10,
                    "geographic_coordinates": {"latitude": lat, "longitude": lon},
                },
            }
        }
        resp = await self._http().post(
            f"{_BASE}/stays/search", json=body, headers=self._headers()
        )
        if resp.status_code >= 400:
            log.warning("duffel_stays_error", status=resp.status_code, body=resp.text[:200])
            return []
        return self._parse(resp.json(), check_in, check_out, max_results=max_results)

    @staticmethod
    def _parse(
        payload: dict, check_in: date, check_out: date, *, max_results: int = 5
    ) -> list[HotelOffer]:
        results = payload.get("data", {}).get("results", []) or []
        out: list[HotelOffer] = []
        for r in results[:max_results]:
            acc = r.get("accommodation", {}) or {}
            amount = r.get("cheapest_rate_total_amount")
            if amount is None:
                continue
            rating = acc.get("rating")
            out.append(
                HotelOffer(
                    id=str(r.get("id", "")),
                    name=acc.get("name", "Hotel"),
                    price=Money(
                        amount=float(amount),
                        currency=r.get("cheapest_rate_currency", "USD"),
                    ),
                    check_in=check_in.isoformat(),
                    check_out=check_out.isoformat(),
                    rating=str(rating) if rating is not None else None,
                    bookable=True,
                    source="duffel",
                )
            )
        return out

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
