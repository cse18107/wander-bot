"""Web-sourced hotel suggestions via Tavily + LLM extraction.

Interim lodging source until Duffel Stays access is granted. These are REAL hotels
found on the web with *estimated* prices (not live/bookable inventory) — names are
suffixed "(web est.)" and prices are best-effort. Untrusted web content passes
through the content guardrail before the LLM sees it.
"""

from __future__ import annotations

from datetime import date

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from wanderbot.domain import HotelOffer, Money
from wanderbot.observability.logging import get_logger
from wanderbot.providers.tavily import TavilyProvider

log = get_logger(__name__)


class _HotelCandidate(BaseModel):
    name: str
    estimated_total_price: float | None = Field(None, description="Total stay price if derivable")
    currency: str = "USD"
    area: str | None = None


class _HotelCandidates(BaseModel):
    items: list[_HotelCandidate] = Field(default_factory=list)


class TavilyHotelProvider:
    def __init__(self, tavily: TavilyProvider, model: BaseChatModel):
        self._tavily = tavily
        self._model = model

    async def search_web_hotels(
        self,
        city: str | None,
        check_in: date,
        check_out: date,
        adults: int = 1,
        currency: str = "USD",
    ) -> list[HotelOffer]:
        if not city:
            return []
        query = f"recommended mid-range hotels to stay in {city} with approximate nightly prices"
        try:
            results = await self._tavily.search(query, max_results=5)
        except Exception as exc:
            log.warning("tavily_hotel_search_failed", error=str(exc))
            return []
        if not results:
            return []

        from wanderbot.security.engine import guard_content

        raw = "\n\n".join(f"{r.title}\n{r.content}\nURL: {r.url}" for r in results)[:4000]
        safe = await guard_content(raw)  # untrusted web content

        prompt = (
            f"From these web results about hotels in {city}, extract up to 5 real, named "
            f"hotels suitable for {adults} adult(s), {check_in} to {check_out}. Estimate the "
            f"TOTAL stay price in {currency} if the text supports it, else leave null. Only "
            f"include actual hotel names that appear in the text.\n\n{safe.text}"
        )
        try:
            cands: _HotelCandidates = await self._model.with_structured_output(
                _HotelCandidates
            ).ainvoke(prompt)
        except Exception as exc:
            log.warning("tavily_hotel_extract_failed", error=str(exc))
            return []

        offers: list[HotelOffer] = []
        for c in cands.items:
            amount = float(c.estimated_total_price) if c.estimated_total_price else 0.0
            offers.append(
                HotelOffer(
                    id=f"web-{abs(hash(c.name)) % 10**8}",
                    name=f"{c.name} (web est.)",
                    price=Money(amount=amount, currency=(c.currency or currency)),
                    check_in=check_in.isoformat(),
                    check_out=check_out.isoformat(),
                    rating=c.area,
                    bookable=False,
                    source="web",
                    note="Live availability unavailable — web estimate, not bookable.",
                )
            )
        return offers
