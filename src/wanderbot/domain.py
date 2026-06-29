"""Shared domain models used across providers, tools, and agents.

These are the normalized shapes the system speaks internally, independent of any
single vendor's response format. Provider adapters map vendor JSON -> these.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field

IataCode = Annotated[str, Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")]


class Money(BaseModel):
    amount: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"


class FlightSegment(BaseModel):
    origin: str
    destination: str
    departure_at: str
    arrival_at: str
    carrier: str
    flight_number: str
    # Human-friendly detail so the UI never shows bare IATA codes.
    origin_name: str | None = None  # e.g. "Netaji Subhas Chandra Bose Intl"
    origin_city: str | None = None  # e.g. "Kolkata"
    destination_name: str | None = None
    destination_city: str | None = None
    carrier_name: str | None = None  # e.g. "China Eastern Airlines"


class FlightOffer(BaseModel):
    id: str
    price: Money
    segments: list[FlightSegment]
    stops: int
    duration: str | None = None

    @property
    def origin(self) -> str:
        return self.segments[0].origin if self.segments else ""

    @property
    def destination(self) -> str:
        return self.segments[-1].destination if self.segments else ""


class FlightSearchQuery(BaseModel):
    origin: IataCode
    destination: IataCode
    departure_date: date
    return_date: date | None = None
    adults: int = Field(default=1, ge=1, le=9)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    max_results: int = Field(default=5, ge=1, le=20)


class HotelOffer(BaseModel):
    id: str
    name: str
    price: Money
    check_in: str
    check_out: str
    rating: str | None = None
    # Provenance: bookable=True for live inventory (Duffel/Amadeus); False for
    # web-sourced suggestions (Tavily fallback) the UI renders inactive.
    bookable: bool = True
    source: str | None = None  # "duffel" | "amadeus" | "web"
    note: str | None = None


class HotelSearchQuery(BaseModel):
    city_code: IataCode
    check_in: date
    check_out: date
    adults: int = Field(default=1, ge=1, le=9)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    max_results: int = Field(default=5, ge=1, le=20)


class Activity(BaseModel):
    id: str
    name: str
    price: Money | None = None
    rating: str | None = None
    description: str | None = None
    booking_link: str | None = None


class GeoPoint(BaseModel):
    name: str
    latitude: float
    longitude: float
    iata_city_code: str | None = None
