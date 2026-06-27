"""Wanderbot MCP server (standalone process).

Exposes real travel tools over the Model Context Protocol. Runs on stdio by
default (used by tests and the embedded client) and can serve streamable HTTP in
deployment. Every tool validates input and is rate-limited server-side; all data
comes from real provider APIs (no mocks).
"""

from __future__ import annotations

from datetime import date

from mcp.server.fastmcp import FastMCP

from mcp_server.ratelimit import TokenBucket
from wanderbot.domain import FlightSearchQuery
from wanderbot.observability.logging import configure_logging, get_logger
from wanderbot.providers.amadeus.flights import AmadeusFlightProvider
from wanderbot.providers.base import ProviderError

configure_logging()
log = get_logger("mcp_server")

mcp = FastMCP("wanderbot-travel")

_flight_provider = AmadeusFlightProvider()
_flight_bucket = TokenBucket(rate_per_sec=5, burst=10)


@mcp.tool()
async def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    adults: int = 1,
    currency: str = "USD",
    max_results: int = 5,
) -> str:
    """Search real flight offers between two airports (IATA codes) for given dates."""
    if not _flight_bucket.allow():
        return "Rate limited: too many flight searches, slow down."
    try:
        query = FlightSearchQuery(
            origin=origin,
            destination=destination,
            departure_date=date.fromisoformat(departure_date),
            return_date=date.fromisoformat(return_date) if return_date else None,
            adults=adults,
            currency=currency,
            max_results=max_results,
        )
    except Exception as exc:
        return f"Invalid flight query: {exc}"

    try:
        offers = await _flight_provider.search_flights(query)
    except ProviderError as exc:
        return f"Flight provider error: {exc}"

    if not offers:
        return f"No flights {query.origin}->{query.destination} on {query.departure_date}."

    return "Flight options:\n" + "\n".join(
        f"{o.origin}->{o.destination} | {o.price} | {o.stops} stop(s) "
        f"| {o.segments[0].carrier}{o.segments[0].flight_number}"
        for o in offers
    )


if __name__ == "__main__":
    log.info("mcp_server_start", transport="stdio")
    mcp.run()
