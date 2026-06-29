"""Structured-output schemas for agent I/O.

``TripBrief`` is what we coerce free-form user text into via
``llm.with_structured_output`` — no fragile string parsing downstream.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class TripStop(BaseModel):
    """One destination in a (possibly multi-stop) trip."""

    destination_city: str
    days: int | None = Field(None, description="Nights/days at this stop if stated")
    start_date: date | None = Field(None, description="Arrival date at this stop if stated")


class TripBrief(BaseModel):
    """Normalized intent extracted from the user's request."""

    origin_city: str | None = Field(None, description="Departure city or IATA code")
    destination_city: str | None = Field(None, description="Destination city or IATA code")
    stops: list[TripStop] = Field(
        default_factory=list,
        description="Ordered destinations for a multi-stop trip, e.g. [Tokyo 3d, Shanghai 4d]. "
        "Leave empty for a single-destination trip.",
    )
    start_date: date | None = None
    end_date: date | None = None
    duration_days: int | None = Field(None, description="Trip length in days if stated, e.g. '4 days'")
    adults: int = Field(1, ge=1, le=9)
    budget_total: float | None = Field(None, description="Total budget in the user's currency")
    currency: str = "USD"
    interests: list[str] = Field(default_factory=list, description="e.g. food, hiking, museums")
    notes: str | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v: object) -> str:
        # LLMs sometimes emit "" or a name; fall back to USD for anything non-ISO.
        if isinstance(v, str) and len(v.strip()) == 3:
            return v.strip().upper()
        return "USD"

    @field_validator("adults", mode="before")
    @classmethod
    def _clamp_adults(cls, v: object) -> int:
        try:
            return min(max(int(v), 1), 9)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 1

    def is_searchable(self) -> bool:
        return bool(self.destination_city and self.start_date)
