"""Provider interfaces.

The interface exists for resilience and provider-swap (Amadeus -> Duffel, etc.),
NOT to substitute fake data. Every concrete adapter calls a real API.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from wanderbot.domain import (
    Activity,
    FlightOffer,
    FlightSearchQuery,
    GeoPoint,
    HotelOffer,
    HotelSearchQuery,
)


class ProviderError(RuntimeError):
    """Raised when an upstream provider fails in a non-retryable way."""


@runtime_checkable
class FlightProvider(Protocol):
    async def search_flights(self, query: FlightSearchQuery) -> list[FlightOffer]: ...


@runtime_checkable
class HotelProvider(Protocol):
    async def search_hotels(self, query: HotelSearchQuery) -> list[HotelOffer]: ...


@runtime_checkable
class ActivityProvider(Protocol):
    async def search_activities(self, lat: float, lon: float) -> list[Activity]: ...


@runtime_checkable
class GeoProvider(Protocol):
    async def geocode_city(self, keyword: str) -> GeoPoint | None: ...
