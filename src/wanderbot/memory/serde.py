"""Checkpoint serializer that explicitly trusts Wanderbot's own state types.

LangGraph warns when it deserializes custom Pydantic types it hasn't been told to
allow (a future-proofing/security measure). We register our state types so the
checkpointer round-trips them cleanly without warnings.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# (module, qualname) pairs for every custom type stored in graph state.
_ALLOWED = [
    ("wanderbot.agents.schemas", "TripBrief"),
    ("wanderbot.domain", "Money"),
    ("wanderbot.domain", "FlightSegment"),
    ("wanderbot.domain", "FlightOffer"),
    ("wanderbot.domain", "HotelOffer"),
    ("wanderbot.domain", "Activity"),
    ("wanderbot.domain", "GeoPoint"),
    ("wanderbot.agents.state", "Selections"),
    ("wanderbot.agents.state", "BudgetState"),
    ("wanderbot.agents.state", "Itinerary"),
    ("wanderbot.agents.state", "ItineraryDay"),
    ("wanderbot.agents.state", "TransportRoute"),
    ("wanderbot.agents.state", "TransportLeg"),
]


def build_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED)


def build_memory_saver() -> MemorySaver:
    return MemorySaver(serde=build_serde())
