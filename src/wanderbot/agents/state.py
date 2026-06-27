"""Typed graph state.

State is modeled explicitly (not stuffed into message history) so routing is
deterministic, context stays cheap, and the graph is testable. Each field has a
clear owner among the specialist nodes.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from wanderbot.agents.schemas import TripBrief
from wanderbot.domain import Activity, FlightOffer, GeoPoint, HotelOffer

BudgetStatus = Literal["unknown", "ok", "over"]


class Selections(BaseModel):
    flight: FlightOffer | None = None
    hotel: HotelOffer | None = None
    activities: list[Activity] = Field(default_factory=list)

    def total_cost(self) -> float:
        total = 0.0
        if self.flight:
            total += self.flight.price.amount
        # Only count bookable lodging; web-estimate suggestions don't inflate the
        # real, reservable total.
        if self.hotel and self.hotel.bookable:
            total += self.hotel.price.amount
        total += sum(a.price.amount for a in self.activities if a.price)
        return round(total, 2)

    def currency(self, default: str = "USD") -> str:
        """The currency of the priced selections (flight is the anchor)."""
        if self.flight:
            return self.flight.price.currency
        if self.hotel:
            return self.hotel.price.currency
        for a in self.activities:
            if a.price:
                return a.price.currency
        return default


class BudgetState(BaseModel):
    target: float | None = None
    currency: str = "USD"
    status: BudgetStatus = "unknown"
    total: float = 0.0
    local_total: float | None = None
    local_currency: str | None = None


class ItineraryDay(BaseModel):
    day: int
    title: str
    items: list[str] = Field(default_factory=list)


class Itinerary(BaseModel):
    summary: str
    headline: str | None = Field(None, description="Punchy 2-4 word title, e.g. 'London Heritage Week'")
    days: list[ItineraryDay] = Field(default_factory=list)
    local_food: list[str] = Field(default_factory=list, description="Famous local dishes to try")
    occasions: list[str] = Field(
        default_factory=list, description="Festivals/events during the travel dates"
    )
    best_known_for: str | None = None
    description: str | None = Field(None, description="2-3 sentence overview of the destination")
    local_language: str | None = None
    local_currency: str | None = None
    local_currency_code: str | None = Field(None, description="ISO 4217 code, e.g. INR, GBP, JPY")


class TransportLeg(BaseModel):
    """One leg of a (possibly multi-leg / break) journey to the destination."""

    mode: str  # e.g. "Train", "Shared jeep", "Taxi", "Bus", "Ferry", "Walk"
    icon: str = "trip_origin"  # Material Symbols name, e.g. "train", "local_taxi"
    from_place: str
    to_place: str
    duration: str | None = None  # short, e.g. "10h"
    cost: str | None = None  # short, in local currency, e.g. "₹1,200"


class TransportRoute(BaseModel):
    """A way to reach the destination — direct or a break journey of several legs."""

    title: str  # e.g. "Train + Taxi via New Jalpaiguri (NJP)"
    legs: list[TransportLeg] = Field(default_factory=list)
    total_duration: str | None = None
    total_cost: str | None = None  # local currency
    note: str | None = None  # e.g. "Cheapest", "Fastest", "Most scenic"


class TripState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    home_city: str | None
    brief: TripBrief | None
    geo: GeoPoint | None
    research: str | None
    images: list[str]
    day_images: dict[str, object]
    memories: list[str]
    flight_options: list[FlightOffer]
    nearby_options: list[FlightOffer]
    transport_options: list[TransportRoute]
    flights_searched: bool
    flight_action: str | None
    selections: Selections
    budget: BudgetState
    itinerary: Itinerary | None
    next: str
    approvals: dict[str, str]
    iterations: int
    replan_note: str | None
    done: dict[str, bool]


def initial_state(
    message: AnyMessage, user_id: str = "anonymous", home_city: str | None = None
) -> TripState:
    return TripState(
        messages=[message],
        user_id=user_id,
        home_city=home_city,
        brief=None,
        geo=None,
        research=None,
        images=[],
        day_images={},
        memories=[],
        flight_options=[],
        nearby_options=[],
        transport_options=[],
        flights_searched=False,
        flight_action=None,
        selections=Selections(),
        budget=BudgetState(),
        itinerary=None,
        next="",
        approvals={},
        iterations=0,
        replan_note=None,
        done={},
    )
