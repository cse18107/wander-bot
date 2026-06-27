"""Amadeus city geocoding (real) — resolves a city name to lat/long + IATA code."""

from __future__ import annotations

from wanderbot.domain import GeoPoint
from wanderbot.providers.amadeus.base import AmadeusBase


class AmadeusGeoProvider(AmadeusBase):
    async def geocode_city(self, keyword: str) -> GeoPoint | None:
        data = await self._get(
            "/v1/reference-data/locations/cities",
            {"keyword": keyword, "max": 1},
        )
        items = data.get("data", [])
        if not items:
            return None
        item = items[0]
        geo = item.get("geoCode", {})
        return GeoPoint(
            name=item.get("name", keyword),
            latitude=float(geo.get("latitude", 0.0)),
            longitude=float(geo.get("longitude", 0.0)),
            iata_city_code=item.get("iataCode"),
        )
