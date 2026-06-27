"""Live sandbox test — hits the real Amadeus test environment.

Skipped unless WB_AMADEUS_CLIENT_ID/SECRET are present. Run with: pytest -m live
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from wanderbot.domain import FlightSearchQuery
from wanderbot.providers.amadeus.flights import AmadeusFlightProvider

pytestmark = pytest.mark.live

_HAS_CREDS = bool(os.getenv("WB_AMADEUS_CLIENT_ID") and os.getenv("WB_AMADEUS_CLIENT_SECRET"))


@pytest.mark.skipif(not _HAS_CREDS, reason="Amadeus sandbox credentials not configured")
@pytest.mark.asyncio
async def test_real_flight_search_returns_offers() -> None:
    provider = AmadeusFlightProvider()
    try:
        offers = await provider.search_flights(
            FlightSearchQuery(
                origin="JFK",
                destination="LHR",
                departure_date=date.today() + timedelta(days=30),
                adults=1,
            )
        )
    finally:
        await provider.aclose()
    assert offers, "expected real offers from Amadeus sandbox"
    assert offers[0].price.amount > 0
