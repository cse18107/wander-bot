"""Flight search tool exposed to the agent.

Typed Pydantic args + validation. The tool wraps a real ``FlightProvider`` and
returns model-friendly, structured results (or a recoverable error string the
agent can reason about).
"""

from __future__ import annotations

from datetime import date

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from wanderbot.domain import FlightSearchQuery
from wanderbot.observability.logging import get_logger
from wanderbot.providers.amadeus.flights import AmadeusFlightProvider
from wanderbot.providers.base import FlightProvider, ProviderError

log = get_logger(__name__)


class SearchFlightsArgs(BaseModel):
    origin: str = Field(description="Origin IATA airport code, e.g. JFK")
    destination: str = Field(description="Destination IATA airport code, e.g. NRT")
    departure_date: date = Field(description="Outbound date (YYYY-MM-DD)")
    return_date: date | None = Field(None, description="Return date for round trips")
    adults: int = Field(1, ge=1, le=9)
    currency: str = Field("USD")
    max_results: int = Field(5, ge=1, le=10)


def build_search_flights_tool(provider: FlightProvider | None = None) -> StructuredTool:
    provider = provider or AmadeusFlightProvider()

    async def _search(
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date | None = None,
        adults: int = 1,
        currency: str = "USD",
        max_results: int = 5,
    ) -> str:
        try:
            query = FlightSearchQuery(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                adults=adults,
                currency=currency,
                max_results=max_results,
            )
        except Exception as exc:  # validation error -> recoverable for the agent
            return f"Invalid flight query: {exc}"

        try:
            offers = await provider.search_flights(query)
        except ProviderError as exc:
            return f"Flight search temporarily unavailable ({exc}). Try again."

        if not offers:
            return f"No flights found {query.origin}->{query.destination} on {query.departure_date}."

        lines = [
            f"{o.origin}->{o.destination} | {o.price} | {o.stops} stop(s) "
            f"| {o.segments[0].carrier}{o.segments[0].flight_number}"
            for o in offers
        ]
        return "Flight options:\n" + "\n".join(lines)

    return StructuredTool.from_function(
        coroutine=_search,
        name="search_flights",
        description=(
            "Search real flight offers between two airports for given dates. "
            "Use IATA airport codes. Returns priced options with stops and carrier."
        ),
        args_schema=SearchFlightsArgs,
    )
