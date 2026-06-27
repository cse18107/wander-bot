"""Amadeus Hotel Search adapter (real, two-step: by-city -> offers)."""

from __future__ import annotations

from wanderbot.domain import HotelOffer, HotelSearchQuery, Money
from wanderbot.providers.amadeus.base import AmadeusBase
from wanderbot.providers.base import ProviderError


class AmadeusHotelProvider(AmadeusBase):
    async def search_hotels(self, query: HotelSearchQuery) -> list[HotelOffer]:
        # Step 1: resolve hotel ids in the city.
        by_city = await self._get(
            "/v1/reference-data/locations/hotels/by-city",
            {"cityCode": query.city_code.upper()},
        )
        hotel_ids = [h["hotelId"] for h in by_city.get("data", [])][: query.max_results]
        if not hotel_ids:
            return []

        # Step 2: priced offers for those hotels.
        try:
            offers_raw = await self._get(
                "/v3/shopping/hotel-offers",
                {
                    "hotelIds": ",".join(hotel_ids),
                    "checkInDate": query.check_in.isoformat(),
                    "checkOutDate": query.check_out.isoformat(),
                    "adults": query.adults,
                    "currency": query.currency.upper(),
                    "bestRateOnly": "true",
                },
            )
        except ProviderError:
            return []
        return self._parse(offers_raw)

    @staticmethod
    def _parse(payload: dict) -> list[HotelOffer]:
        results: list[HotelOffer] = []
        for entry in payload.get("data", []):
            hotel = entry.get("hotel", {})
            offers = entry.get("offers", [])
            if not offers:
                continue
            offer = offers[0]
            price = offer.get("price", {})
            results.append(
                HotelOffer(
                    id=str(hotel.get("hotelId", "")),
                    name=hotel.get("name", "Unknown hotel"),
                    price=Money(
                        amount=float(price.get("total", 0)),
                        currency=price.get("currency", "USD"),
                    ),
                    check_in=offer.get("checkInDate", ""),
                    check_out=offer.get("checkOutDate", ""),
                    rating=hotel.get("rating"),
                )
            )
        return results
