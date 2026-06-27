"""Dependency bundle for the graph.

Holds the model + real providers the specialist nodes need. Everything is
injectable so deterministic graph tests can pass fakes; production builds the
real Amadeus adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from wanderbot.memory.store import LongTermMemory
    from wanderbot.providers.base import (
        ActivityProvider,
        FlightProvider,
        GeoProvider,
        HotelProvider,
    )
    from wanderbot.rag.research import Researcher


@dataclass
class Deps:
    model: "BaseChatModel"
    flights: "FlightProvider"
    geo: "GeoProvider"
    hotels: "HotelProvider | None" = None  # primary (live, bookable)
    hotels_fallback: object | None = None  # Tavily web suggestions (non-bookable)
    activities: "ActivityProvider | None" = None
    memory: "LongTermMemory | None" = None
    researcher: "Researcher | None" = None
    fx: object | None = None  # FrankfurterFXProvider


def build_default_deps() -> Deps:
    from wanderbot.config import get_settings
    from wanderbot.llm_factory import build_chat_model
    from wanderbot.memory.runtime import get_memory_store
    from wanderbot.providers.tavily import TavilyProvider
    from wanderbot.rag.knowledge_base import build_retriever
    from wanderbot.rag.research import Researcher

    settings = get_settings()
    model = build_chat_model()

    # --- Flights (config-selectable; Duffel default) ---
    if settings.flight_provider == "amadeus":
        from wanderbot.providers.amadeus.flights import AmadeusFlightProvider

        flights = AmadeusFlightProvider()
    else:
        from wanderbot.providers.duffel.flights import DuffelFlightProvider

        flights = DuffelFlightProvider()

    # --- Geocoding (config-selectable; Open-Meteo keyless default) ---
    if settings.geo_provider == "amadeus":
        from wanderbot.providers.amadeus.geo import AmadeusGeoProvider

        geo = AmadeusGeoProvider()
    else:
        from wanderbot.providers.openmeteo import OpenMeteoGeoProvider

        geo = OpenMeteoGeoProvider()

    # --- Hotels: a primary live source + a Tavily web fallback ---
    # Primary = real bookable inventory (Duffel Stays / Amadeus). Fallback = Tavily
    # web suggestions, shown inactive when the primary returns nothing.
    hotels = None
    hotels_fallback = None
    activities = None
    hp = settings.hotel_provider

    def _build_tavily_hotels():  # noqa: ANN202
        from wanderbot.providers.tavily import TavilyProvider
        from wanderbot.providers.tavily_hotels import TavilyHotelProvider

        return TavilyHotelProvider(TavilyProvider(), model)

    if hp != "none" and settings.tavily_api_key is not None:
        hotels_fallback = _build_tavily_hotels()

    if hp == "duffel" and settings.duffel_api_key is not None:
        from wanderbot.providers.duffel.stays import DuffelStaysProvider

        hotels = DuffelStaysProvider()
    elif hp == "amadeus" and (
        settings.amadeus_client_id is not None and settings.amadeus_client_secret is not None
    ):
        from wanderbot.providers.amadeus.hotels import AmadeusHotelProvider

        hotels = AmadeusHotelProvider()
    elif hp == "tavily":
        # Tavily explicitly chosen as the only source.
        hotels = hotels_fallback
        hotels_fallback = None

    # --- Activities (Amadeus only; enabled if credentials present) ---
    if settings.amadeus_client_id is not None and settings.amadeus_client_secret is not None:
        from wanderbot.providers.amadeus.activities import AmadeusActivityProvider

        activities = AmadeusActivityProvider()

    return Deps(
        model=model,
        flights=flights,
        geo=geo,
        hotels=hotels,
        hotels_fallback=hotels_fallback,
        activities=activities,
        memory=get_memory_store(),
        researcher=Researcher(build_retriever(), web=TavilyProvider()),
        fx=_build_fx(),
    )


def _build_fx():  # noqa: ANN202
    from wanderbot.providers.fx import FrankfurterFXProvider

    return FrankfurterFXProvider()
