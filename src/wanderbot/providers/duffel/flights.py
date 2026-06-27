"""Duffel Flight Offers adapter (real, sandbox-ready).

Duffel has instant self-serve signup with a free test mode (`duffel_test_` tokens).
Maps the Duffel offer-request response into our normalized ``FlightOffer``.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from wanderbot.config import Settings, get_settings
from wanderbot.domain import FlightOffer, FlightSearchQuery, FlightSegment, Money
from wanderbot.observability.logging import get_logger
from wanderbot.providers.base import ProviderError

log = get_logger(__name__)

_BASE = "https://api.duffel.com"


class DuffelFlightProvider:
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

    async def resolve_place(self, query: str | None) -> str | None:
        """Resolve a city/airport name to an IATA code via Duffel Places."""
        if not query:
            return None
        try:
            resp = await self._http().get(
                f"{_BASE}/places/suggestions",
                params={"query": query},
                headers=self._headers(),
            )
        except Exception:  # pragma: no cover - network
            return None
        if resp.status_code >= 400:
            log.warning("duffel_places_error", status=resp.status_code, query=query)
            return None
        data = resp.json().get("data", []) or []
        # Prefer a city code (covers all its airports), else the first airport.
        for kind in ("city", "airport"):
            for d in data:
                if d.get("type") == kind and d.get("iata_code"):
                    return str(d["iata_code"])
        return None

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        reraise=True,
    )
    async def search_flights(self, query: FlightSearchQuery) -> list[FlightOffer]:
        slices = [
            {
                "origin": query.origin.upper(),
                "destination": query.destination.upper(),
                "departure_date": query.departure_date.isoformat(),
            }
        ]
        if query.return_date:
            slices.append(
                {
                    "origin": query.destination.upper(),
                    "destination": query.origin.upper(),
                    "departure_date": query.return_date.isoformat(),
                }
            )
        body = {
            "data": {
                "slices": slices,
                "passengers": [{"type": "adult"} for _ in range(query.adults)],
                "cabin_class": "economy",
            }
        }

        resp = await self._http().post(
            f"{_BASE}/air/offer_requests?return_offers=true",
            json=body,
            headers=self._headers(),
        )
        if resp.status_code >= 400:
            log.warning("duffel_error", status=resp.status_code, body=resp.text[:300])
            if resp.status_code == 429:
                raise ProviderError("duffel_rate_limited")
            raise ProviderError(f"duffel flight search failed ({resp.status_code})")

        return self._parse(resp.json(), max_results=query.max_results)

    @staticmethod
    def _parse(payload: dict, *, max_results: int = 5) -> list[FlightOffer]:
        offers = payload.get("data", {}).get("offers", []) or []
        results: list[FlightOffer] = []
        for offer in offers[:max_results]:
            slices = offer.get("slices", [])
            segments: list[FlightSegment] = []
            for sl in slices:
                for seg in sl.get("segments", []):
                    carrier = (seg.get("marketing_carrier") or {}).get("iata_code", "")
                    segments.append(
                        FlightSegment(
                            origin=seg["origin"]["iata_code"],
                            destination=seg["destination"]["iata_code"],
                            departure_at=seg.get("departing_at", ""),
                            arrival_at=seg.get("arriving_at", ""),
                            carrier=carrier,
                            flight_number=str(seg.get("marketing_carrier_flight_number", "")),
                        )
                    )
            stops = max(len(slices[0].get("segments", [])) - 1, 0) if slices else 0
            results.append(
                FlightOffer(
                    id=str(offer.get("id", "")),
                    price=Money(
                        amount=float(offer.get("total_amount", 0)),
                        currency=offer.get("total_currency", "USD"),
                    ),
                    segments=segments,
                    stops=stops,
                )
            )
        return results

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
