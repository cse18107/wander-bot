"""Amadeus Flight Offers Search adapter.

Maps the Amadeus v2 flight-offers response into our normalized ``FlightOffer``.
Retries transient failures with jittered backoff; surfaces 4xx as ProviderError.
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from wanderbot.config import Settings, get_settings
from wanderbot.domain import FlightOffer, FlightSearchQuery, FlightSegment, Money
from wanderbot.observability.logging import get_logger
from wanderbot.providers.amadeus.token_manager import AmadeusTokenManager
from wanderbot.providers.base import ProviderError

log = get_logger(__name__)


class AmadeusFlightProvider:
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
    async def search_flights(self, query: FlightSearchQuery) -> list[FlightOffer]:
        token = await self._tokens.get_token()
        params: dict[str, str | int] = {
            "originLocationCode": query.origin.upper(),
            "destinationLocationCode": query.destination.upper(),
            "departureDate": query.departure_date.isoformat(),
            "adults": query.adults,
            "currencyCode": query.currency.upper(),
            "max": query.max_results,
        }
        if query.return_date:
            params["returnDate"] = query.return_date.isoformat()

        resp = await self._http().get(
            f"{self._settings.amadeus_base_url}/v2/shopping/flight-offers",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code >= 400:
            log.warning("amadeus_flight_error", status=resp.status_code, body=resp.text[:300])
            if resp.status_code == 429:
                raise ProviderError("amadeus_rate_limited")
            raise ProviderError(f"amadeus flight search failed ({resp.status_code})")

        return self._parse(resp.json())

    @staticmethod
    def _parse(payload: dict) -> list[FlightOffer]:
        offers: list[FlightOffer] = []
        for raw in payload.get("data", []):
            segments: list[FlightSegment] = []
            itineraries = raw.get("itineraries", [])
            for itin in itineraries:
                for seg in itin.get("segments", []):
                    segments.append(
                        FlightSegment(
                            origin=seg["departure"]["iataCode"],
                            destination=seg["arrival"]["iataCode"],
                            departure_at=seg["departure"]["at"],
                            arrival_at=seg["arrival"]["at"],
                            carrier=seg.get("carrierCode", ""),
                            flight_number=str(seg.get("number", "")),
                        )
                    )
            stops = max(len(itineraries and itineraries[0].get("segments", [])) - 1, 0)
            price = raw.get("price", {})
            offers.append(
                FlightOffer(
                    id=str(raw.get("id", "")),
                    price=Money(
                        amount=float(price.get("grandTotal", price.get("total", 0))),
                        currency=price.get("currency", "USD"),
                    ),
                    segments=segments,
                    stops=stops,
                    duration=itineraries[0].get("duration") if itineraries else None,
                )
            )
        return offers

    async def aclose(self) -> None:
        await self._tokens.aclose()
        if self._owns_client and self._client is not None:
            await self._client.aclose()
