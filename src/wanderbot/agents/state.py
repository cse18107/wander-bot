"""Typed graph state.

State is modeled explicitly (not stuffed into message history) so routing is
deterministic, context stays cheap, and the graph is testable. Each field has a
clear owner among the specialist nodes.
"""

from __future__ import annotations

from datetime import date
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


class BudgetTier(BaseModel):
    """A rough cost tier for the trip (e.g. 'Very affordable', 'Mid luxury', 'Luxury')."""

    name: str
    total: float  # whole-trip total in the destination's local currency
    home_total: float | None = None  # same, converted to the traveller's home currency
    note: str | None = None  # short: hotel class + dining style


class BudgetState(BaseModel):
    target: float | None = None
    currency: str = "USD"
    status: BudgetStatus = "unknown"
    total: float = 0.0
    local_total: float | None = None
    local_currency: str | None = None
    # The figure shown to the user, in their HOME country's currency. When nothing
    # bookable is priced, this is an estimate (estimated=True).
    home_total: float | None = None
    home_currency: str | None = None
    estimated: bool = False
    # Rough Tavily-grounded cost tiers; the plan defaults to the affordable one.
    tiers: list[BudgetTier] = Field(default_factory=list)
    selected_tier: str | None = None


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
    estimated_total: float | None = Field(
        None,
        description="Realistic mid-range TOTAL cost for the whole trip — lodging, meals, "
        "local transport and sightseeing — in local_currency_code. Exclude long-haul airfare.",
    )
    home_currency_code: str | None = Field(
        None, description="ISO 4217 currency code of the traveller's HOME city's country"
    )


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


class TripLeg(BaseModel):
    """A resolved stop in the trip: where, from where, and when."""

    destination_city: str
    origin_city: str | None = None  # previous stop (or home for the first leg)
    start_date: date | None = None
    end_date: date | None = None
    days: int | None = None


class HopOption(BaseModel):
    """A unified transport choice for one hop — a flight, train, ferry, etc."""

    id: str
    mode: str  # "Flight" | "Train" | "Ferry" | "Bus" | "Road" | "Mixed"
    icon: str = "flight"  # Material Symbols name
    title: str  # e.g. "MU0556 · 2 stops" or "Shinkansen + ferry"
    from_code: str | None = None
    to_code: str | None = None
    from_city: str | None = None
    to_city: str | None = None
    from_name: str | None = None  # full airport name
    to_name: str | None = None
    carrier_name: str | None = None
    depart: str | None = None
    arrive: str | None = None
    duration: str | None = None
    stops: int | None = None
    price: float | None = None
    currency: str | None = None
    currency_name: str | None = None
    price_home: float | None = None  # price converted to the traveller's home currency
    currency_home: str | None = None
    note: str | None = None
    flight_id: str | None = None  # set if this is a real bookable Duffel flight
    legs: list[TransportLeg] = Field(default_factory=list)  # for multi-leg ground journeys


class LegPlan(BaseModel):
    """The finished plan for one leg of a multi-stop trip."""

    destination_city: str
    start_date: date | None = None
    end_date: date | None = None
    transport: HopOption | None = None  # how the traveller reaches this stop
    itinerary: "Itinerary | None" = None
    hotel: HotelOffer | None = None
    budget: BudgetState | None = None
    images: list[str] = Field(default_factory=list)
    day_images: dict[str, object] = Field(default_factory=dict)


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
    local_trip: bool
    flights_searched: bool
    flight_action: str | None
    # Multi-stop trips: ordered legs, the one being planned, finished leg plans,
    # and the current hop's unified transport choices (flights + ground).
    legs: list[TripLeg]
    leg_index: int
    leg_plans: list[LegPlan]
    legs_complete: bool
    home_currency_code: str | None  # the traveller's home currency, fixed across all legs
    hop_options: list[HopOption]
    hop_action: str | None
    chosen_transport: HopOption | None  # ground route the user picked (no flight)
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
        local_trip=False,
        flights_searched=False,
        flight_action=None,
        legs=[],
        leg_index=0,
        leg_plans=[],
        legs_complete=False,
        home_currency_code=None,
        hop_options=[],
        hop_action=None,
        chosen_transport=None,
        selections=Selections(),
        budget=BudgetState(),
        itinerary=None,
        next="",
        approvals={},
        iterations=0,
        replan_note=None,
        done={},
    )
