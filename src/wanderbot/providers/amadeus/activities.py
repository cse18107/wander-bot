"""Amadeus Tours & Activities adapter (real) — activities near a coordinate."""

from __future__ import annotations

from wanderbot.domain import Activity, Money
from wanderbot.providers.amadeus.base import AmadeusBase


class AmadeusActivityProvider(AmadeusBase):
    async def search_activities(self, lat: float, lon: float) -> list[Activity]:
        data = await self._get(
            "/v1/shopping/activities",
            {"latitude": lat, "longitude": lon, "radius": 20},
        )
        return self._parse(data)

    @staticmethod
    def _parse(payload: dict) -> list[Activity]:
        results: list[Activity] = []
        for raw in payload.get("data", [])[:15]:
            price_raw = raw.get("price")
            price = None
            if price_raw and price_raw.get("amount"):
                price = Money(
                    amount=float(price_raw["amount"]),
                    currency=price_raw.get("currencyCode", "USD"),
                )
            results.append(
                Activity(
                    id=str(raw.get("id", "")),
                    name=raw.get("name", "Activity"),
                    price=price,
                    rating=raw.get("rating"),
                    description=(raw.get("shortDescription") or "")[:200] or None,
                    booking_link=raw.get("bookingLink"),
                )
            )
        return results
