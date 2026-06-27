"""Test doubles (fakes) for deterministic graph tests.

NOTE: these are TEST-ONLY fixtures so graph logic can be verified without network
or an LLM. Production code never uses fakes — providers always hit real APIs.
"""

from __future__ import annotations

from datetime import date

from wanderbot.agents.schemas import TripBrief
from wanderbot.agents.state import Itinerary, ItineraryDay
from wanderbot.domain import (
    Activity,
    FlightOffer,
    FlightSegment,
    GeoPoint,
    HotelOffer,
    Money,
)


class _FakeStructured:
    def __init__(self, value: object):
        self._value = value

    async def ainvoke(self, _input: object) -> object:
        return self._value


class FakeModel:
    """Returns preset structured outputs keyed by requested schema."""

    def __init__(self, brief: TripBrief, itinerary: Itinerary | None = None):
        self._brief = brief
        self._itinerary = itinerary or Itinerary(
            summary="Test trip",
            days=[ItineraryDay(day=1, title="Arrival", items=["Settle in"])],
        )

    def with_structured_output(self, schema: type) -> _FakeStructured:
        if schema is TripBrief:
            return _FakeStructured(self._brief)
        return _FakeStructured(self._itinerary)


class FakeFlights:
    def __init__(self, price: float = 600.0):
        self._price = price

    async def search_flights(self, query: object) -> list[FlightOffer]:
        return [
            FlightOffer(
                id="F1",
                price=Money(amount=self._price, currency="USD"),
                segments=[
                    FlightSegment(
                        origin="JFK",
                        destination="NRT",
                        departure_at="2026-10-12T09:00:00",
                        arrival_at="2026-10-13T13:00:00",
                        carrier="NH",
                        flight_number="9",
                    )
                ],
                stops=0,
            )
        ]


class FakeHotels:
    def __init__(self, price: float = 400.0):
        self._price = price

    async def search_hotels(self, query: object) -> list[HotelOffer]:
        return [
            HotelOffer(
                id="H1",
                name="Test Hotel",
                price=Money(amount=self._price, currency="USD"),
                check_in="2026-10-12",
                check_out="2026-10-15",
            )
        ]


class FakeActivities:
    def __init__(self, prices: list[float] | None = None):
        self._prices = prices if prices is not None else [80.0, 120.0]

    async def search_activities(self, lat: float, lon: float) -> list[Activity]:
        return [
            Activity(id=f"A{i}", name=f"Activity {i}", price=Money(amount=p, currency="USD"))
            for i, p in enumerate(self._prices)
        ]


class FakeGeo:
    async def geocode_city(self, keyword: str) -> GeoPoint:
        return GeoPoint(name=keyword, latitude=35.68, longitude=139.69, iata_city_code="TYO")


async def run_until_reserve(graph, config, inputs):
    """Drive a graph past the flight-selection pause (picking the first option)
    and return the state once it pauses for reserve approval."""
    from wanderbot.agents import routing

    await graph.ainvoke(inputs, config)
    snap = await graph.aget_state(config)
    if snap.next == (routing.SELECT_FLIGHT,):
        opts = snap.values.get("flight_options") or []
        sel = snap.values["selections"]
        chosen = opts[0] if opts else None
        await graph.aupdate_state(
            config,
            {
                "selections": sel.model_copy(update={"flight": chosen}),
                "flight_action": "select" if chosen else "proceed",
            },
        )
        return await graph.ainvoke(None, config)
    return snap.values


def sample_brief(budget_total: float | None = None) -> TripBrief:
    return TripBrief(
        origin_city="JFK",
        destination_city="NRT",
        start_date=date(2026, 10, 12),
        end_date=date(2026, 10, 15),
        adults=2,
        budget_total=budget_total,
        currency="USD",
        interests=["food", "hiking"],
    )
