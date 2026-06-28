"""Specialist node implementations.

Each node owns one slice of the plan and returns a partial state update. Nodes are
async and take their dependencies via the :class:`Deps` bundle so they're testable
with injected fakes.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from wanderbot.agents.bundle import Deps
from wanderbot.agents.schemas import TripBrief
from wanderbot.agents.state import (
    BudgetState,
    Itinerary,
    ItineraryDay,
    Selections,
    TransportRoute,
    TripState,
)
from wanderbot.domain import (
    FlightSearchQuery,
    HotelSearchQuery,
)
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)


def _to_code(value: str | None) -> str | None:
    if value and len(value) == 3 and value.isalpha():
        return value.upper()
    return None


def _pick_web(hotels: list) -> object | None:
    """Prefer a priced web suggestion; otherwise the first one (price unknown)."""
    priced = [h for h in hotels if h.price.amount > 0]
    return min(priced, key=lambda h: h.price.amount, default=None) or (
        hotels[0] if hotels else None
    )


def _same_city(
    origin_name: str | None, dest_name: str | None,
    origin_code: str | None, dest_code: str | None,
) -> bool:
    """True when origin and destination are the same place (a local trip)."""
    if origin_code and dest_code and origin_code == dest_code:
        return True
    o = (origin_name or "").strip().lower()
    d = (dest_name or "").strip().lower()
    return bool(o and d and o == d)


def _last_human(state: TripState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


class _TransportResearch(BaseModel):
    routes: list[TransportRoute] = Field(default_factory=list)


class Nodes:
    def __init__(self, deps: Deps):
        self.deps = deps

    # --- intake ---------------------------------------------------------
    async def intake(self, state: TripState) -> TripState:
        text = _last_human(state)
        today = date.today()
        structured = self.deps.model.with_structured_output(TripBrief)
        prompt = (
            f"Today's date is {today.isoformat()}. Extract a structured trip brief "
            "from the user's message. Capture the trip length as duration_days if a "
            "number of days/nights is stated (e.g. '4 days' -> duration_days=4). Only "
            "set start_date if the user gives an actual start date or month; if no "
            "start date is mentioned, leave start_date null (we will ask). Resolve a "
            "stated month to the 1st of its next occurrence. Keep city names as "
            "written (do not convert to codes).\n\nMessage:\n" + text
        )
        try:
            brief: TripBrief = await structured.ainvoke(prompt)  # type: ignore[assignment]
        except Exception as exc:
            # A malformed LLM extraction must not 500 the stream; ask to rephrase.
            log.warning("intake_parse_failed", error=str(exc))
            return {
                "brief": TripBrief(),  # not searchable -> router sends to RESPOND
                "budget": BudgetState(),
                "selections": Selections(),
            }

        # Default the departure city to the user's saved home city if not stated.
        if not brief.origin_city and state.get("home_city"):
            brief.origin_city = state["home_city"]

        # If a start date IS known but no end, derive it from the duration.
        if brief.start_date and not brief.end_date:
            days = brief.duration_days or 5
            brief.end_date = brief.start_date + timedelta(days=days)

        budget = BudgetState(target=brief.budget_total, currency=brief.currency)

        # Long-term memory: recall this user's durable preferences (cross-trip).
        memories: list[str] = []
        user_id = state.get("user_id")
        if self.deps.memory is not None and user_id:
            try:
                memories = await self.deps.memory.search(user_id, text, k=5)
                # Persist stated interests as durable preferences for future trips.
                for interest in brief.interests:
                    await self.deps.memory.add(user_id, f"enjoys {interest}", kind="preference")
            except Exception as exc:  # pragma: no cover - resilience
                log.warning("memory_recall_failed", error=str(exc))

        log.info(
            "intake_parsed",
            destination=brief.destination_city,
            searchable=brief.is_searchable(),
            recalled=len(memories),
        )
        return {"brief": brief, "budget": budget, "selections": Selections(), "memories": memories}

    # --- research -------------------------------------------------------
    async def research(self, state: TripState) -> TripState:
        brief = state["brief"]
        assert brief is not None
        geo = None
        note = f"Planning a trip to {brief.destination_city}."
        if brief.destination_city:
            try:
                geo = await self.deps.geo.geocode_city(brief.destination_city)
            except Exception as exc:  # pragma: no cover - resilience
                log.warning("geocode_failed", error=str(exc))
        if geo:
            note += f" Coordinates {geo.latitude:.2f},{geo.longitude:.2f}."

        # Grounded research (RAG + optional live web) with citations.
        if self.deps.researcher is not None and brief.destination_city:
            interests = ", ".join(brief.interests) or "general travel"
            query = f"{brief.destination_city} best time to visit {interests}"
            try:
                result = await self.deps.researcher.research(query)
                if result.notes:
                    note += "\n\nResearch:\n" + result.notes
                if result.citations:
                    note += "\n\nSources: " + "; ".join(result.citations)
            except Exception as exc:  # pragma: no cover - resilience
                log.warning("research_failed", error=str(exc))

        # Imagery for the UI (one Tavily call, distributed across hero + day cards).
        images: list[str] = []
        if self.deps.researcher is not None and brief.destination_city:
            images = await self.deps.researcher.fetch_images(
                f"{brief.destination_city} travel landmarks cityscape", n=8
            )
        return {"geo": geo, "research": note, "images": images}

    def _mark(self, state: TripState, step: str) -> dict[str, bool]:
        return {**state.get("done", {}), step: True}

    async def _resolve_code(self, value: str | None, geo_fallback: str | None = None) -> str | None:
        """City/airport name -> IATA code: direct code, geo code, or provider lookup."""
        code = _to_code(value)
        if code:
            return code
        if geo_fallback:
            return geo_fallback
        resolver = getattr(self.deps.flights, "resolve_place", None)
        if resolver and value:
            try:
                return await resolver(value)
            except Exception as exc:  # pragma: no cover - resilience
                log.warning("place_resolve_failed", value=value, error=str(exc))
        return None

    async def _research_transport(self, brief: TripBrief) -> list[TransportRoute]:
        """No flights? Research realistic ground transport (incl. break journeys).

        Many destinations have no airport — the only way in may be train, bus,
        shared jeep, taxi, or ferry, sometimes via a railhead in another town.
        Uses live web search for context, then asks the model for structured
        routes with per-leg cost/duration in the local currency.
        """
        origin = (brief.origin_city or "").strip() if brief else ""
        dest = (brief.destination_city or "").strip() if brief else ""
        if not dest:
            return []
        origin = origin or "the traveller's city"

        web = getattr(self.deps.researcher, "web", None)
        context = ""
        if web is not None:
            try:
                results = await web.search(
                    f"how to reach {dest} from {origin} by train bus taxi shared jeep — "
                    f"nearest railway station and airport, distance, travel time and fare",
                    max_results=5,
                )
                context = "\n".join(
                    f"- {getattr(r, 'title', '')}: {getattr(r, 'content', '')[:300]}"
                    for r in results
                )
            except Exception as exc:  # pragma: no cover - resilience
                log.warning("transport_research_search_failed", error=str(exc))

        prompt = (
            f"A traveller wants to get from {origin} to {dest}"
            + (f" around {brief.start_date.isoformat()}" if brief and brief.start_date else "")
            + ".\n"
            f"{dest} may NOT have an airport. Work out the realistic ways to actually get "
            "there. IMPORTANT: include BREAK JOURNEYS — e.g. a train or flight to the nearest "
            "railhead/airport in a neighbouring town, then a taxi / shared jeep / bus for the "
            "final stretch. Give 2-4 distinct routes (cover the cheapest and the fastest).\n"
            "For EACH route return ordered legs. Each leg has: mode (Train/Flight/Bus/Shared "
            "jeep/Taxi/Ferry/Walk), icon (a Google Material Symbols name like 'train', 'flight', "
            "'directions_bus', 'local_taxi', 'directions_car', 'directions_boat', 'directions_walk'), "
            "from_place, to_place, duration (short, e.g. '10h'), and cost (short, in the LOCAL "
            "currency, e.g. '₹1,200'). Also give the route a short title, a total_duration, a "
            "total_cost (local currency), and a one-word note ('Cheapest'/'Fastest'/'Scenic').\n"
            "Use this live web context where helpful; do not invent stations that don't exist:\n"
            f"{context or '(no extra context)'}"
        )
        try:
            res: _TransportResearch = await self.deps.model.with_structured_output(
                _TransportResearch
            ).ainvoke(prompt)  # type: ignore[assignment]
            return [r for r in (res.routes or []) if r.title and r.legs][:4]
        except Exception as exc:  # pragma: no cover - resilience
            log.warning("transport_research_failed", error=str(exc))
            return []

    # --- flights (search only; user selects in the next step) -----------
    async def flights(self, state: TripState) -> TripState:
        brief = state["brief"]
        assert brief is not None
        geo = state.get("geo")
        origin = await self._resolve_code(brief.origin_city)
        destination = await self._resolve_code(
            brief.destination_city, geo.iata_city_code if geo else None
        )

        # Local trip: origin and destination are the same city (e.g. planning a
        # day out in your own city). There are no flights — and no "how to reach"
        # arrival problem — so skip the whole flight/transport step and go straight
        # to the itinerary. Getting around to each spot is covered per-day in the
        # day-detail drawer.
        if _same_city(brief.origin_city, brief.destination_city, origin, destination):
            log.info("local_trip_skip_transit", city=brief.destination_city)
            done = self._mark(state, "flights")
            return {
                "flight_options": [],
                "nearby_options": [],
                "transport_options": [],
                "flights_searched": True,
                "local_trip": True,
                "done": done,
                "messages": [
                    AIMessage(
                        content=f"{brief.destination_city} is your home city — no flights "
                        "or intercity transport needed, so I'll jump straight to your day plan."
                    )
                ],
            }

        options: list = []
        nearby: list = []
        if origin and destination and brief.start_date:
            trip_len = brief.duration_days or (
                (brief.end_date - brief.start_date).days
                if brief.end_date and brief.start_date
                else 5
            )

            async def _search(dep):  # noqa: ANN001, ANN202
                return await self.deps.flights.search_flights(
                    FlightSearchQuery(
                        origin=origin,
                        destination=destination,
                        departure_date=dep,
                        return_date=dep + timedelta(days=trip_len),
                        adults=brief.adults,
                        currency=brief.currency,
                    )
                )

            try:
                options = sorted(await _search(brief.start_date), key=lambda o: o.price.amount)
            except Exception as exc:
                log.warning("flight_search_failed", error=str(exc))

            # No flights that day -> search +/-5 days (excluding the day, skip past).
            if not options:
                today = date.today()
                dates = [
                    brief.start_date + timedelta(days=d)
                    for d in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5)
                ]
                dates = [d for d in dates if d >= today]
                results = await asyncio.gather(
                    *[_search(d) for d in dates], return_exceptions=True
                )
                for offers in results:
                    if isinstance(offers, list) and offers:
                        nearby.append(min(offers, key=lambda o: o.price.amount))
                nearby.sort(key=lambda o: o.segments[0].departure_at)

        # No air option at all (e.g. destination has no airport) -> research
        # realistic ground transport, including multi-leg break journeys.
        transport: list[TransportRoute] = []
        if not options and not nearby:
            transport = await self._research_transport(brief)

        return {
            "flight_options": options,
            "nearby_options": nearby,
            "transport_options": transport,
            "flights_searched": True,
        }

    # --- select_flight (human-in-the-loop: pick a flight) ---------------
    async def select_flight(self, state: TripState) -> TripState:
        """Runs after the user picks a flight / proceeds / asks to change date.

        Behavior is driven by ``flight_action`` set by the API before resuming.
        """
        action = state.get("flight_action")
        if action == "change_date":
            brief = state["brief"]
            return {
                "flights_searched": False,
                "flight_options": [],
                "flight_action": None,
                "messages": [
                    AIMessage(content=f"Updated start date to {brief.start_date if brief else ''}. "
                              "Searching flights again…")
                ],
            }
        # "select" or "proceed": selections.flight was already set by the API.
        done = self._mark(state, "flights")
        sel = state["selections"]
        msg = (
            f"Flight selected — {sel.flight.price} ({sel.flight.segments[0].carrier}"
            f"{sel.flight.segments[0].flight_number})."
            if sel.flight
            else "Proceeding without a flight."
        )
        return {"done": done, "flight_action": None, "messages": [AIMessage(content=msg)]}

    # --- lodging --------------------------------------------------------
    async def lodging(self, state: TripState) -> TripState:
        brief = state["brief"]
        assert brief is not None
        # Local trip (home city == destination): the traveller already lives here,
        # so there's no stay to book. Skip lodging.
        if state.get("local_trip"):
            return {"done": self._mark(state, "lodging")}
        geo = state.get("geo")
        city_code = (geo.iata_city_code if geo else None) or _to_code(brief.destination_city)
        selections = state["selections"]
        check_in = brief.start_date or date.today() + timedelta(days=30)
        check_out = brief.end_date or check_in + timedelta(days=3)
        done = self._mark(state, "lodging")
        cheapest = None
        currency = selections.currency(brief.currency)

        async def _from_primary() -> object | None:
            provider = self.deps.hotels
            if provider is None:
                return None
            if hasattr(provider, "search_stays") and geo:
                hotels = await provider.search_stays(
                    geo.latitude, geo.longitude, check_in, check_out, brief.adults
                )
                return min(hotels, key=lambda h: h.price.amount, default=None)
            if hasattr(provider, "search_web_hotels"):
                hotels = await provider.search_web_hotels(
                    brief.destination_city, check_in, check_out, brief.adults, currency
                )
                return _pick_web(hotels)
            if hasattr(provider, "search_hotels") and city_code:
                hotels = await provider.search_hotels(
                    HotelSearchQuery(
                        city_code=city_code, check_in=check_in, check_out=check_out,
                        adults=brief.adults, currency=brief.currency,
                    )
                )
                return min(hotels, key=lambda h: h.price.amount, default=None)
            return None

        async def _from_fallback() -> object | None:
            fb = self.deps.hotels_fallback
            if fb is None or not hasattr(fb, "search_web_hotels"):
                return None
            hotels = await fb.search_web_hotels(
                brief.destination_city, check_in, check_out, brief.adults, currency
            )
            return _pick_web(hotels)

        try:
            cheapest = await _from_primary()
            if cheapest is None:
                # Primary (live, bookable) had nothing -> show web suggestions,
                # which carry bookable=False so the UI renders them inactive.
                cheapest = await _from_fallback()
                if cheapest is not None:
                    log.info("hotel_fallback_used", source="web")
        except Exception as exc:
            log.warning("hotel_search_failed", error=str(exc))
        new = selections.model_copy(update={"hotel": cheapest})
        return {"selections": new, "done": done}

    # --- activities -----------------------------------------------------
    async def activities(self, state: TripState) -> TripState:
        geo = state.get("geo")
        selections = state["selections"]
        done = self._mark(state, "activities")
        items: list = []
        if geo and self.deps.activities is not None:
            try:
                items = await self.deps.activities.search_activities(geo.latitude, geo.longitude)
            except Exception as exc:
                log.warning("activity_search_failed", error=str(exc))
        new = selections.model_copy(update={"activities": items[:6]})
        return {"selections": new, "done": done}

    # --- budget ---------------------------------------------------------
    async def budget(self, state: TripState) -> TripState:
        selections = state["selections"]
        budget = state["budget"]
        total = selections.total_cost()
        currency = selections.currency(budget.currency)
        status: str = "ok"
        if budget.target is not None and total > budget.target:
            # Over budget, but only "over" (i.e. trim further) if there's
            # discretionary spend left to cut.
            status = "over" if selections.activities else "ok"
        new_budget = budget.model_copy(
            update={"total": total, "status": status, "currency": currency}
        )
        return {"budget": new_budget}

    # --- replan ---------------------------------------------------------
    async def replan(self, state: TripState) -> TripState:
        """One bounded optimization step: drop the most expensive activity."""
        selections = state["selections"]
        iterations = state.get("iterations", 0) + 1
        priced = [a for a in selections.activities if a.price]
        if priced:
            most_expensive = max(priced, key=lambda a: a.price.amount)  # type: ignore[union-attr]
            remaining = [a for a in selections.activities if a.id != most_expensive.id]
            new = selections.model_copy(update={"activities": remaining})
            note = f"Trimmed '{most_expensive.name}' to fit budget."
        else:
            new = selections
            note = "No discretionary items left to trim; accepting best plan."
        # Reset budget status so the budget node re-evaluates.
        budget = state["budget"].model_copy(update={"status": "unknown"})
        return {"selections": new, "iterations": iterations, "replan_note": note, "budget": budget}

    # --- itinerary ------------------------------------------------------
    async def itinerary(self, state: TripState) -> TripState:
        brief = state["brief"]
        selections = state["selections"]
        assert brief is not None
        structured = self.deps.model.with_structured_output(Itinerary)
        research = (state.get("research") or "")[:1500]
        prompt = (
            "Build a concise day-by-day holiday itinerary as structured data, plus "
            "recommendations. Give a punchy 2-4 word headline (e.g. 'London Heritage "
            "Week'). For each day give a title and 2-4 specific items. Also "
            "fill: local_food (famous dishes of this destination to try), occasions "
            "(any festivals/holidays/events happening DURING the travel dates, else "
            "empty), best_known_for (one short line), description (2-3 sentence "
            "overview of the destination), local_language (the main language(s) "
            "spoken), local_currency (the currency name and ISO code), and "
            "local_currency_code (the ISO 4217 code only, e.g. INR, GBP, JPY).\n"
            f"Destination: {brief.destination_city}\n"
            f"Dates: {brief.start_date} to {brief.end_date}\n"
            f"Hotel: {selections.hotel.name if selections.hotel else 'n/a'}\n"
            f"Interests: {', '.join(brief.interests) or 'general'}\n"
            f"Known preferences: {', '.join(state.get('memories') or []) or 'none'}\n"
            f"Grounding (research notes):\n{research}"
        )
        try:
            itin: Itinerary = await structured.ainvoke(prompt)  # type: ignore[assignment]
        except Exception:  # pragma: no cover - deterministic fallback
            itin = Itinerary(
                summary=f"Trip to {brief.destination_city}",
                days=[ItineraryDay(day=1, title="Arrival", items=["Check in", "Explore"])],
            )
        total = selections.total_cost()
        budget = state["budget"]
        currency = selections.currency(budget.currency)

        # Convert the budget into the destination's local currency (real FX).
        local_code = itin.local_currency_code
        local_total = budget.local_total
        if self.deps.fx is not None and local_code:
            try:
                local_total = await self.deps.fx.convert(total, currency, local_code)
            except Exception as exc:  # pragma: no cover - resilience
                log.warning("fx_convert_failed", error=str(exc))
        new_budget = budget.model_copy(
            update={"local_total": local_total, "local_currency": local_code}
        )

        local_str = f" (≈ {local_total:.0f} {local_code})" if local_total is not None and local_code else ""
        msg = AIMessage(
            content=f"Draft itinerary ready ({total:.0f} {currency}{local_str}). Approve to reserve."
        )
        return {"itinerary": itin, "budget": new_budget, "messages": [msg]}

    # --- image curator (relevant photo per day) -------------------------
    async def curate_images(self, state: TripState) -> TripState:
        """Pick a relevant image per day from its title + landmarks, plus a hero.

        A dedicated step so imagery actually matches each day's content rather than
        reusing a generic destination photo. One targeted search per day + hero.
        """
        done = self._mark(state, "images")
        itin = state.get("itinerary")
        brief = state["brief"]
        if self.deps.researcher is None or itin is None or brief is None:
            return {"done": done}

        dest = brief.destination_city or ""
        batch = state.get("images") or []

        async def first_image(query: str) -> str:
            try:
                imgs = await self.deps.researcher.fetch_images(query, n=2)
                return imgs[0] if imgs else ""
            except Exception as exc:  # pragma: no cover - resilience
                log.warning("curate_image_failed", error=str(exc))
                return ""

        hero = await first_image(f"{dest} skyline cityscape travel") or (batch[0] if batch else "")
        day_urls: list[str] = []
        for i, d in enumerate(itin.days):
            landmarks = " ".join(d.items[:2])
            query = f"{dest} {d.title} {landmarks}".strip()[:120]
            url = await first_image(query)
            if not url and batch:
                url = batch[(i + 1) % len(batch)]  # fallback to the batch
            day_urls.append(url)

        log.info("images_curated", days=len(day_urls))
        return {"done": done, "day_images": {"hero": hero, "days": day_urls}}

    # --- reserve (human-in-the-loop) ------------------------------------
    async def reserve(self, state: TripState) -> TripState:
        """Execute only after human approval.

        The graph is compiled with ``interrupt_before=[reserve]`` so the run
        pauses (checkpointed) before this node and surfaces an approval request to
        the caller (the UI). The caller resumes after setting ``approvals.reserve``.
        Because the only money-moving step is gated here, prompt injection alone can
        never trigger an irreversible booking.
        """
        approvals = {**state.get("approvals", {})}
        approved = approvals.get("reserve") == "approved"
        if "reserve" not in approvals:
            approvals["reserve"] = "declined"
        text = (
            "Plan approved ✓ — note: no real booking was made. Actual reservation, "
            "payment, and ticketing are not implemented in this demo; this step only "
            "records your approval. Wiring real booking (e.g. Duffel order creation) "
            "would happen here."
            if approved
            else "Okay, nothing reserved. Let me know if you'd like to revise the plan."
        )
        return {"approvals": approvals, "messages": [AIMessage(content=text)]}

    def approval_request(self, state: TripState) -> dict[str, object]:
        """Payload the UI shows at the HITL pause."""
        selections = state["selections"]
        return {
            "type": "approval_request",
            "action": "reserve",
            "total": selections.total_cost(),
            "flight": selections.flight.id if selections.flight else None,
            "hotel": selections.hotel.name if selections.hotel else None,
        }

    # --- clarify (human-in-the-loop: ask for origin and/or dates) -------
    async def clarify(self, state: TripState) -> TripState:
        """Runs after the user supplies a missing field (origin or start date).

        End date is derived from the stated duration so we never ask for it.
        """
        brief = state["brief"]
        assert brief is not None
        if brief.start_date and not brief.end_date:
            days = brief.duration_days or 5
            brief = brief.model_copy(update={"end_date": brief.start_date + timedelta(days=days)})
        msgs = []
        if brief.origin_city and brief.start_date:
            msgs = [
                AIMessage(
                    content=f"Got it — planning {brief.destination_city} from "
                    f"{brief.origin_city}, {brief.start_date} to {brief.end_date}."
                )
            ]
        return {"brief": brief, "messages": msgs}

    # --- respond (need more info) ---------------------------------------
    async def respond(self, state: TripState) -> TripState:
        msg = AIMessage(
            content="Could you share your destination and travel dates so I can start planning?"
        )
        return {"messages": [msg]}
