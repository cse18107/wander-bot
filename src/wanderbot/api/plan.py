"""/plan endpoint — drives the multi-agent supervisor graph over SSE.

Streams per-node progress, selection/itinerary updates, and the human-approval
pause. The conversation is checkpointed, so the approval arrives as a separate
request and resumes the same run.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from wanderbot.agents import routing
from wanderbot.agents.state import Itinerary, initial_state
from wanderbot.api.deps import get_principal, get_rate_limiter
from wanderbot.observability.logging import get_logger
from wanderbot.security import engine as guard_engine
from wanderbot.security.audit import audit
from wanderbot.security.auth import Principal
from wanderbot.security.guardrails import Decision
from wanderbot.security.ratelimit import RateLimiter
from wanderbot.storage.plans import (
    get_plan,
    list_plans,
    plan_data_from_state,
    save_day_detail,
    upsert_plan,
)

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["plan"])

_graph = None


def _get_graph():  # noqa: ANN202
    global _graph
    if _graph is None:
        from wanderbot.agents.graph import build_graph
        from wanderbot.memory.serde import build_memory_saver

        _graph = build_graph(checkpointer=build_memory_saver())
    return _graph


class PlanRequest(BaseModel):
    message: str
    thread_id: str = "default"


class ApproveRequest(BaseModel):
    thread_id: str = "default"
    decision: str = "approved"  # approved | declined


class ClarifyRequest(BaseModel):
    thread_id: str = "default"
    answer: str


class SelectFlightRequest(BaseModel):
    thread_id: str = "default"
    flight_id: str | None = None  # None = proceed without a flight


class ChangeDateRequest(BaseModel):
    thread_id: str = "default"
    answer: str


class _ParsedDate(BaseModel):
    value: date | None = None


async def _parse_start_date(answer: str) -> date | None:
    a = answer.strip()
    try:
        return date.fromisoformat(a)
    except ValueError:
        pass
    try:
        from wanderbot.llm_factory import build_chat_model

        today = date.today()
        res: _ParsedDate = await build_chat_model().with_structured_output(_ParsedDate).ainvoke(
            f"Today is {today.isoformat()}. Convert this trip start-date answer to a "
            f"concrete FUTURE date (YYYY-MM-DD): '{a}'"
        )  # type: ignore[assignment]
        return res.value
    except Exception as exc:  # pragma: no cover
        log.warning("date_parse_failed", error=str(exc))
        return None


def _thread(principal: Principal, thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": f"{principal.user_id}:{thread_id}"}}


def _offer_to_dict(o, with_date: bool = False) -> dict[str, Any]:
    seg = o.segments[0]
    d: dict[str, Any] = {
        "id": o.id,
        "price": o.price.model_dump(),
        "origin": seg.origin,
        "destination": seg.destination,
        "depart": seg.departure_at,
        "arrive": seg.arrival_at,
        "carrier": seg.carrier,
        "number": seg.flight_number,
        "stops": o.stops,
    }
    if with_date:
        d["date"] = seg.departure_at[:10] if seg.departure_at else None
    return d


def _emit_node_update(node: str, payload: dict) -> list[dict]:
    events: list[dict] = [{"event": "step", "data": json.dumps({"node": node})}]
    if isinstance(payload, dict):
        images = payload.get("images")
        if images:
            events.append({"event": "images", "data": json.dumps(images)})
        day_images = payload.get("day_images")
        if day_images:
            events.append({"event": "day_images", "data": json.dumps(day_images)})
        sel = payload.get("selections")
        if sel is not None:
            events.append({"event": "selections", "data": sel.model_dump_json()})
        itin = payload.get("itinerary")
        if itin is not None:
            events.append({"event": "itinerary", "data": itin.model_dump_json()})
        budget = payload.get("budget")
        if budget is not None:
            events.append({"event": "budget", "data": budget.model_dump_json()})
        for msg in payload.get("messages", []) or []:
            if isinstance(msg, AIMessage):
                events.append({"event": "message", "data": str(msg.content)})
    return events


async def _stream_run(graph, inputs, config) -> AsyncIterator[dict]:
    async for update in graph.astream(inputs, config=config, stream_mode="updates"):
        for node, payload in update.items():
            for ev in _emit_node_update(node, payload):
                yield ev

    # Persist the plan (per user) whenever an itinerary exists.
    state = await graph.aget_state(config)
    try:
        thread = config["configurable"]["thread_id"]
        uid, pid = thread.split(":", 1)
        existing = await get_plan(pid, uid)
        data = plan_data_from_state(
            state.values, existing["data"].get("day_details") if existing else None
        )
        if data:
            itin = data["itinerary"]
            brief = data.get("brief") or {}
            hero = (data.get("day_images") or {}).get("hero") or (data.get("images") or [None])[0]
            title = itin.get("headline") or (itin.get("summary", "Trip").split(".")[0])
            await upsert_plan(pid, uid, title, brief.get("destination_city"), hero, data)
    except Exception as exc:  # pragma: no cover - persistence best-effort
        log.warning("plan_save_failed", error=str(exc))

    # Paused for clarification, flight selection, or reserve approval?
    if state.next == (routing.SELECT_FLIGHT,):
        options = state.values.get("flight_options") or []
        if options:
            payload = [_offer_to_dict(o) for o in options]
            yield {"event": "flight_options", "data": json.dumps(payload)}
        else:
            brief = state.values.get("brief")
            nearby = state.values.get("nearby_options") or []
            transport = state.values.get("transport_options") or []
            yield {
                "event": "no_flights",
                "data": json.dumps(
                    {
                        "date": brief.start_date.isoformat() if brief and brief.start_date else None,
                        "destination": brief.destination_city if brief else None,
                        "nearby": [_offer_to_dict(o, with_date=True) for o in nearby],
                        "transport": [t.model_dump() for t in transport],
                    }
                ),
            }
        yield {"event": "done", "data": "[DONE]"}
        return
    if state.next == (routing.CLARIFY,):
        brief = state.values.get("brief")
        dest = brief.destination_city if brief else "your destination"
        if brief and not brief.origin_city:
            field = "origin"
            question = f"Where will you be flying from for your trip to {dest}? (your city or nearest airport)"
        else:
            field = "start_date"
            dur = brief.duration_days if brief else None
            question = f"When would you like to start your trip to {dest}?"
            if dur:
                question += f" (You said {dur} days — I'll calculate the end date.)"
        yield {
            "event": "clarification_required",
            "data": json.dumps({"field": field, "question": question}),
        }
    elif state.next == (routing.RESERVE,):
        sel = state.values.get("selections")
        payload = {
            "type": "approval_request",
            "total": sel.total_cost() if sel else 0,
            "flight": (sel.flight.id if sel and sel.flight else None),
            "hotel": (sel.hotel.name if sel and sel.hotel else None),
        }
        yield {"event": "approval_required", "data": json.dumps(payload)}
    yield {"event": "done", "data": "[DONE]"}


@router.post("/plan")
async def plan(
    req: PlanRequest,
    principal: Principal = Depends(get_principal),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> EventSourceResponse:
    if not await limiter.allow(f"plan:{principal.user_id}", limit=20, window_s=60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")

    rail = await guard_engine.guard_input(req.message)
    audit("plan_request", principal.user_id, decision=rail.decision.value, reasons=rail.reasons)
    if rail.decision is Decision.BLOCK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "request blocked by input guardrail")

    from wanderbot.storage.users import get_user

    user = await get_user(principal.user_id)
    home = user.get("home_city") if user else None

    graph = _get_graph()
    config = _thread(principal, req.thread_id)
    inputs = initial_state(
        HumanMessage(content=rail.text), user_id=principal.user_id, home_city=home
    )
    return EventSourceResponse(_stream_run(graph, inputs, config))


@router.post("/plan/clarify")
async def clarify(
    req: ClarifyRequest,
    principal: Principal = Depends(get_principal),
) -> EventSourceResponse:
    graph = _get_graph()
    config = _thread(principal, req.thread_id)
    snap = await graph.aget_state(config)
    brief = snap.values.get("brief")
    if brief is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no trip in progress to clarify")

    # Apply the answer to the first missing field: origin, then start date.
    if not brief.origin_city:
        origin = req.answer.strip()
        updated = brief.model_copy(update={"origin_city": origin})
        from wanderbot.storage.users import set_home_city

        await set_home_city(principal.user_id, origin)  # remember for next time
        audit("plan_clarify", principal.user_id, origin=origin)
    else:
        start = await _parse_start_date(req.answer) or (date.today() + timedelta(days=30))
        days = brief.duration_days or (
            (brief.end_date - brief.start_date).days
            if brief.start_date and brief.end_date
            else 5
        )
        updated = brief.model_copy(update={"start_date": start, "end_date": start + timedelta(days=days)})
        audit("plan_clarify", principal.user_id, start=start.isoformat())
    await graph.aupdate_state(config, {"brief": updated})
    return EventSourceResponse(_stream_run(graph, None, config))


@router.post("/plan/select_flight")
async def select_flight(
    req: SelectFlightRequest,
    principal: Principal = Depends(get_principal),
) -> EventSourceResponse:
    graph = _get_graph()
    config = _thread(principal, req.thread_id)
    snap = await graph.aget_state(config)
    options = (snap.values.get("flight_options") or []) + (snap.values.get("nearby_options") or [])
    sel = snap.values.get("selections")
    chosen = next((o for o in options if o.id == req.flight_id), None) if req.flight_id else None
    new_sel = sel.model_copy(update={"flight": chosen})

    update: dict[str, Any] = {"selections": new_sel, "flight_action": "select" if chosen else "proceed"}
    # If the user picked a flight on a different day, shift the trip dates to match.
    if chosen:
        dep = chosen.segments[0].departure_at
        chosen_date = date.fromisoformat(dep[:10]) if dep else None
        brief = snap.values.get("brief")
        if chosen_date and brief and brief.start_date != chosen_date:
            days = brief.duration_days or (
                (brief.end_date - brief.start_date).days
                if brief.end_date and brief.start_date
                else 5
            )
            update["brief"] = brief.model_copy(
                update={"start_date": chosen_date, "end_date": chosen_date + timedelta(days=days)}
            )
    audit("plan_select_flight", principal.user_id, flight=req.flight_id or "none")
    await graph.aupdate_state(config, update)
    return EventSourceResponse(_stream_run(graph, None, config))


@router.post("/plan/change_date")
async def change_date(
    req: ChangeDateRequest,
    principal: Principal = Depends(get_principal),
) -> EventSourceResponse:
    graph = _get_graph()
    config = _thread(principal, req.thread_id)
    snap = await graph.aget_state(config)
    brief = snap.values.get("brief")
    if brief is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no trip in progress")
    start = await _parse_start_date(req.answer) or (date.today() + timedelta(days=30))
    days = brief.duration_days or 5
    updated = brief.model_copy(update={"start_date": start, "end_date": start + timedelta(days=days)})
    audit("plan_change_date", principal.user_id, start=start.isoformat())
    await graph.aupdate_state(config, {"brief": updated, "flight_action": "change_date"})
    return EventSourceResponse(_stream_run(graph, None, config))


class DayDetailRequest(BaseModel):
    thread_id: str = "default"
    day: int


class _PlaceInfo(BaseModel):
    name: str
    how_to_reach: str = ""
    best_vehicle: str = ""


class _WalkablePlace(BaseModel):
    name: str
    walk_time_min: int = 10


class _DayDetailLLM(BaseModel):
    places: list[_PlaceInfo] = []
    street_food: list[str] = []
    restaurants: list[str] = []
    walkable: list[_WalkablePlace] = []


@router.get("/plans")
async def get_plans(principal: Principal = Depends(get_principal)) -> list[dict[str, Any]]:
    return await list_plans(principal.user_id)


@router.get("/plans/{plan_id}")
async def get_one_plan(
    plan_id: str, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    plan = await get_plan(plan_id, principal.user_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    return {"id": plan["id"], "title": plan["title"], "data": plan["data"]}


@router.post("/plan/day_detail")
async def day_detail(
    req: DayDetailRequest,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    plan = await get_plan(req.thread_id, principal.user_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    data = plan["data"]
    cached = data.get("day_details", {}).get(str(req.day))
    if cached:
        return cached  # instant on reopen

    itin = data.get("itinerary")
    brief = data.get("brief") or {}
    geo = data.get("geo")
    if not itin or req.day < 1 or req.day > len(itin.get("days", [])):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid day")
    day = itin["days"][req.day - 1]
    day = type("D", (), {"day": day["day"], "title": day["title"], "items": day.get("items", [])})
    dest = brief.get("destination_city") or ""

    from wanderbot.llm_factory import build_chat_model

    prompt = (
        f"Day {day.day} — '{day.title}' — of a trip to {dest}. Planned items: "
        f"{', '.join(day.items)}.\n"
        "Produce structured deep-dive details:\n"
        "- places: up to 4 notable places for this day; for each give how_to_reach "
        "(from the city centre) and best_vehicle (e.g. metro, taxi, walk, shared jeep).\n"
        "- street_food: 3-5 famous street foods to try here.\n"
        "- restaurants: 3-5 well-regarded restaurants.\n"
        "- walkable: places reachable on foot from a central point, each with an "
        "approximate walk_time_min.\nBe concise and realistic."
    )
    llm: _DayDetailLLM = await build_chat_model().with_structured_output(_DayDetailLLM).ainvoke(
        prompt
    )  # type: ignore[assignment]

    # Real seasonal weather (Open-Meteo archive). brief/geo are plain dicts here.
    weather = None
    start, end = brief.get("start_date"), brief.get("end_date")
    if geo and start and end:
        from wanderbot.providers.weather import OpenMeteoWeatherProvider

        try:
            weather = await OpenMeteoWeatherProvider().typical_weather(
                float(geo["latitude"]),
                float(geo["longitude"]),
                date.fromisoformat(start),
                date.fromisoformat(end),
            )
        except Exception as exc:  # pragma: no cover
            log.warning("weather_failed", error=str(exc))

    # Real images per place (Tavily).
    from wanderbot.providers.tavily import TavilyProvider

    tav = TavilyProvider()
    places_out: list[dict[str, Any]] = []
    gallery: list[str] = []
    for p in llm.places[:4]:
        url = None
        try:
            imgs = await tav.images(f"{p.name} {dest}", max_results=2)
            url = imgs[0].url if imgs else None
        except Exception:
            url = None
        if url:
            gallery.append(url)
        places_out.append(
            {"name": p.name, "how_to_reach": p.how_to_reach, "best_vehicle": p.best_vehicle, "image": url}
        )

    detail = {
        "day": day.day,
        "title": day.title,
        "places": places_out,
        "weather": weather["summary"] if weather else None,
        "weather_detail": weather,
        "street_food": llm.street_food,
        "restaurants": llm.restaurants,
        "walkable": [w.model_dump() for w in llm.walkable],
        "images": gallery,
    }
    # Cache so reopening the day is instant and free.
    await save_day_detail(req.thread_id, principal.user_id, req.day, detail)
    return detail


class AskRequest(BaseModel):
    thread_id: str = "default"
    question: str
    history: list[dict[str, str]] = []


def _message_text(msg: Any) -> str:
    """Extract plain text from a chat message whose content may be a string or a
    list of content blocks (Gemini/Anthropic style)."""
    content = getattr(msg, "content", msg)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for c in content:
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, dict) and c.get("text"):
                parts.append(str(c["text"]))
        return " ".join(p for p in parts if p).strip()
    return str(content).strip()


def _plan_context(data: dict[str, Any]) -> str:
    itin = data.get("itinerary") or {}
    brief = data.get("brief") or {}
    sel = data.get("selections") or {}
    bud = data.get("budget") or {}
    lines = [
        f"Destination: {brief.get('destination_city')}",
        f"Dates: {brief.get('start_date')} to {brief.get('end_date')}",
        f"Summary: {itin.get('summary')}",
    ]
    flight = sel.get("flight")
    if flight and flight.get("segments"):
        s = flight["segments"][0]
        lines.append(
            f"Flight: {s['origin']}->{s['destination']} "
            f"{flight['price']['amount']} {flight['price']['currency']}"
        )
    hotel = sel.get("hotel")
    if hotel:
        lines.append(f"Hotel: {hotel['name']} ({hotel['price']['amount']} {hotel['price']['currency']})")
    if bud:
        lines.append(f"Budget total: {bud.get('total')} {bud.get('currency')}")
    for d in itin.get("days", []):
        lines.append(f"Day {d['day']} — {d['title']}: " + "; ".join(d.get("items", [])))
    if itin.get("local_food"):
        lines.append("Famous food: " + ", ".join(itin["local_food"]))
    if itin.get("occasions"):
        lines.append("Occasions: " + ", ".join(itin["occasions"]))
    return "\n".join(x for x in lines if x)


class _PlanEdit(BaseModel):
    itinerary: Itinerary
    remove_hotel: bool = False


class _PlaceItem(BaseModel):
    name: str
    price: float | None = None
    currency: str | None = None
    note: str | None = None


class _AttachArgs(BaseModel):
    places: list[_PlaceItem]
    per_subject: int = 1


class _PlacesExtract(BaseModel):
    places: list[_PlaceItem] = []


class _OptionStat(BaseModel):
    icon: str  # Material Symbols name chosen by the model, e.g. "schedule", "payments"
    value: str  # short value, e.g. "25–30 min", "£3–6 / person"


class _Option(BaseModel):
    icon: str  # Material Symbols name, e.g. "directions_subway", "directions_bus", "local_taxi"
    title: str  # e.g. "Piccadilly Line"
    from_label: str | None = None  # left endpoint of the route line, e.g. "Hotel"
    to_label: str | None = None  # right endpoint, e.g. "LHR"
    stats: list[_OptionStat] = []  # time, cost, etc. — model decides which to include
    note: str | None = None  # optional one-liner, e.g. "Cheapest" / "Fastest"


class _OptionsArgs(BaseModel):
    options: list[_Option]
    heading: str | None = None  # optional caption, e.g. "Getting to LHR from your hotel"


async def run_trip_agent(
    plan: dict[str, Any], principal: Principal, question: str, history: list[dict[str, str]]
) -> dict[str, Any]:
    """Tool-using assistant for a trip: answers, web search, and plan edits.

    Shared by /plan/ask and the chat-thread message endpoint. Returns
    {"answer", "plan"} where "plan" is the updated plan data if it was modified.
    """
    rail = await guard_engine.guard_input(question)
    if rail.decision is Decision.BLOCK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "question blocked by guardrail")

    from langchain_core.tools import StructuredTool
    from langgraph.prebuilt import create_react_agent

    from wanderbot.llm_factory import build_chat_model
    from wanderbot.providers.tavily import TavilyProvider

    data = plan["data"]
    dest = (data.get("brief") or {}).get("destination_city") or ""
    changed: dict[str, Any] = {"plan": None}
    cards: list[dict[str, Any]] = []
    model = build_chat_model()

    default_ccy = (data.get("itinerary") or {}).get("local_currency_code")

    async def _attach_images(places: list[Any], per_subject: int = 1) -> str:
        """Attach photo cards (hotels/places) with optional price in local currency."""
        tav = TavilyProvider()
        n = max(1, min(per_subject, 8))
        for raw in (places or [])[:6]:
            p = raw if isinstance(raw, dict) else raw.model_dump()
            name = (p.get("name") or "").strip()
            if not name:
                continue
            try:
                imgs = await tav.images(f"{name} {dest}".strip(), max_results=n + 2)
                urls = [i.url for i in imgs[:n]]
            except Exception:
                urls = []
            card: dict[str, Any] = {"kind": "image", "label": name, "images": urls}
            if p.get("price") is not None:
                card["price"] = p["price"]
                card["currency"] = p.get("currency") or default_ccy
            if p.get("note"):
                card["note"] = p["note"]
            cards.append(card)
        return f"Attached {len(cards)} card(s); the UI renders them."

    async def _show_options(options: list[Any], heading: str | None = None) -> str:
        """Render comparison cards (transport, tickets, passes) — the model picks icons/layout."""
        items: list[dict[str, Any]] = []
        for raw in (options or [])[:8]:
            o = raw if isinstance(raw, dict) else raw.model_dump()
            title = (o.get("title") or "").strip()
            if not title:
                continue
            stats = []
            for s in (o.get("stats") or [])[:4]:
                sd = s if isinstance(s, dict) else s.model_dump()
                val = (sd.get("value") or "").strip()
                if val:
                    stats.append({"icon": (sd.get("icon") or "info").strip(), "value": val})
            items.append({
                "icon": (o.get("icon") or "trip_origin").strip(),
                "title": title,
                "from_label": (o.get("from_label") or None),
                "to_label": (o.get("to_label") or None),
                "stats": stats,
                "note": (o.get("note") or None),
            })
        if items:
            cards.append({"kind": "options", "heading": (heading or None), "options": items})
        return f"Showing {len(items)} option card(s); the UI renders them."

    async def _web_search(query: str) -> str:
        """Search the web for current info (events, opening hours, weather, prices)."""
        try:
            results = await TavilyProvider().search(query, max_results=4)
            safe = await guard_engine.guard_content(
                "\n".join(f"{r.title}: {r.content[:200]} ({r.url})" for r in results)
            )
            return safe.text or "No results found."
        except Exception as exc:  # pragma: no cover
            return f"Search unavailable: {exc}"

    async def _modify_plan(change: str) -> str:
        """Apply a change to the trip (e.g. edit a day's activities, remove the hotel)."""
        itin = data.get("itinerary") or {}
        brief = data.get("brief") or {}
        sel = data.get("selections") or {}
        prompt = (
            f"Current trip to {brief.get('destination_city')} "
            f"({brief.get('start_date')}–{brief.get('end_date')}).\n"
            f"Current itinerary JSON:\n{json.dumps(itin)[:2500]}\n"
            f"Current hotel: {sel.get('hotel', {}).get('name') if sel.get('hotel') else 'none'}\n\n"
            f"Apply this change: {change}\n"
            "Return the FULL updated itinerary (keep unaffected days unchanged). "
            "Set remove_hotel=true ONLY if the user clearly rejects the current hotel."
        )
        try:
            edit: _PlanEdit = await model.with_structured_output(_PlanEdit).ainvoke(prompt)  # type: ignore[assignment]
        except Exception as exc:  # pragma: no cover
            return f"Could not apply the change: {exc}"
        data["itinerary"] = edit.itinerary.model_dump(mode="json")
        if edit.remove_hotel and data.get("selections"):
            data["selections"]["hotel"] = None
        title = data["itinerary"].get("headline") or data["itinerary"].get("summary", "Trip").split(".")[0]
        await upsert_plan(plan["id"], principal.user_id, title, brief.get("destination_city"), plan["hero"], data)
        changed["plan"] = data
        return "Done — I've updated the plan."

    tools = [
        StructuredTool.from_function(coroutine=_web_search, name="web_search",
            description="Search the web for current information (events, hours, weather, prices)."),
        StructuredTool.from_function(coroutine=_modify_plan, name="modify_plan",
            description="Apply a change to the trip plan — edit a day's activities, swap focus, or remove the hotel. Pass the user's requested change as text."),
        StructuredTool.from_function(coroutine=_attach_images, name="attach_images", args_schema=_AttachArgs,
            description="Attach photo cards to your reply. places = list of {name, price (optional, for the requested duration), currency (ISO code), note (optional, short)}. per_subject = images each (1 for a list, 6 to show many of one place). ALWAYS price in the destination's LOCAL currency."),
        StructuredTool.from_function(coroutine=_show_options, name="show_options", args_schema=_OptionsArgs,
            description=(
                "Render visual comparison cards for a set of options — transport routes, ticket types, "
                "passes, tours — instead of writing a text list. YOU design each card: pick the most fitting "
                "Material Symbols icon name for the mode (e.g. directions_subway, train, directions_bus, "
                "local_taxi, directions_car, directions_walk, pedal_bike, directions_boat, flight). "
                "Each option = {icon, title, from_label, to_label, stats:[{icon, value}], note}. "
                "from_label/to_label draw a route line — keep them SHORT (1-2 words, e.g. 'Hotel' -> "
                "'LHR'); never put a full hotel name here. "
                "stats are the data chips — choose a fitting icon per stat: 'schedule' for time, "
                "'payments' or 'sell' for cost, 'directions' for distance, 'star' for rating. "
                "Keep stat values short ('25–30 min', '£3–6 / person'). Use destination LOCAL currency. "
                "ALWAYS include a cost stat for every option, and only include modes that actually "
                "exist for this route (not every place has an airport — it may be train/bus/taxi/ferry only)."
            )),
    ]
    system = (
        "You are Voyager, a concise, friendly travel assistant for THIS specific trip. "
        "Answer questions about the plan from the details below. Keep replies short.\n"
        "TOOLS — use them, don't describe them:\n"
        "• web_search — for live facts (opening hours, events, weather, prices).\n"
        "• modify_plan — when the user wants to change the trip ('change day 3', "
        "'I don't want this hotel').\n"
        "• show_options — whenever the user wants to COMPARE choices (transport modes, ticket "
        "types, passes, ways to get somewhere) with attributes like time/cost. Call it instead "
        "of writing a bullet list: YOU pick a fitting icon per option and per stat, and the UI "
        "draws each as a card with an icon, a route line and data chips. Then reply with only a "
        "one-line intro — do NOT repeat the options as text.\n"
        "  TRANSPORT RULE: never assume which modes exist. Many destinations have NO airport — "
        "the only way in may be train, bus, taxi, shared jeep, or ferry. Before answering a "
        "'how do I get to / get around X' question, use web_search to find which modes ACTUALLY "
        "serve that specific route, then show ONLY the real ones (skip any that don't exist). "
        "Give EVERY option a cost stat in the local currency (research it if unknown), plus a "
        "time stat. If a mode genuinely isn't available, simply leave it out.\n"
        "• attach_images — to show photos. RULE: whenever your reply lists or recommends "
        "specific hotels, restaurants, or attractions, you MUST call attach_images FIRST "
        "with those exact names (per_subject=1). When the user asks to see more images of a "
        "single place, call attach_images with that name and per_subject=6. The UI renders "
        "the photos (and prices) beside your text — never paste image URLs, and never "
        "list places without first calling attach_images. Put any PRICE on the card (in "
        "the destination's LOCAL currency), not in your text. When you attach a list, "
        "write ONLY a one-line intro and do NOT repeat the names/prices as a "
        "bullet/numbered list — the cards already show name, photo and price.\n"
        "Example: user 'price of each hotel for 2 nights' -> call attach_images(places=[{name, "
        "price, currency}], per_subject=1), then reply with just a one-line intro.\n\n"
        "TRIP PLAN:\n" + _plan_context(data)
    )
    agent = create_react_agent(model, tools, prompt=system)

    msgs: list[Any] = []
    for h in (history or [])[-8:]:
        c = h.get("text", "")
        msgs.append(HumanMessage(content=c) if h.get("role") == "user" else AIMessage(content=c))
    msgs.append(HumanMessage(content=rail.text))

    result = await agent.ainvoke({"messages": msgs})
    answer = _message_text(result["messages"][-1])

    # Safety net: if the model skipped attach_images (or returned an empty reply),
    # extract the named places from BOTH the question and the reply and fetch
    # photos deterministically. This covers "show me more images of X" where the
    # model sometimes returns only a tool intent / empty text.
    ql = question.lower()
    wants_images = any(k in ql for k in ("image", "photo", "picture", "pic", "show me", "see "))
    if not cards and (
        wants_images
        or any(k in ql for k in ("hotel", "resort", "restaurant", "cafe", "place", "list", "stay", "where"))
    ):
        try:
            source = f"User asked: {question}\n\nAssistant reply:\n{answer or '(empty)'}"
            extracted: _PlacesExtract = await model.with_structured_output(_PlacesExtract).ainvoke(
                "Extract the specific named hotels, restaurants, or attractions in question "
                "below, with any price and its currency if stated (max 6; empty if none). "
                "Prefer places the USER named.\n\n" + source
            )  # type: ignore[assignment]
            if extracted.places:
                # "more images of X" -> several photos of the single subject.
                many = "more" in ql and len(extracted.places) == 1
                await _attach_images(extracted.places[:6], 6 if many else 1)
        except Exception:  # pragma: no cover
            pass

    # When any cards are attached, drop redundant bullet/numbered lines from the text —
    # the cards already carry the structured detail.
    if cards:
        kept = [
            ln for ln in answer.split("\n")
            if not (ln.strip()[:1] in "*-•" or re.match(r"^\s*\d+[.)]", ln))
        ]
        stripped = "\n".join(kept).strip()
        if stripped:
            answer = stripped

    # Never return a blank bubble. If we have image cards but no text, write a
    # one-line intro; otherwise give a gentle fallback.
    if not answer.strip():
        image_cards = [c for c in cards if c.get("kind") == "image"]
        if image_cards:
            label = image_cards[0].get("label") or "what you asked about"
            answer = (
                f"Here are some photos of {label}:"
                if len(image_cards) == 1
                else "Here are some photos:"
            )
        else:
            answer = "I couldn't find anything to show for that — could you rephrase?"

    out = await guard_engine.guard_output(answer)
    return {
        "answer": out.text if out.allowed else "Sorry, I can't help with that.",
        "plan": changed["plan"],
        "cards": cards or None,
    }


@router.post("/plan/ask")
async def ask(
    req: AskRequest,
    principal: Principal = Depends(get_principal),
) -> dict[str, Any]:
    plan = await get_plan(req.thread_id, principal.user_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")
    return await run_trip_agent(plan, principal, req.question, req.history)


@router.post("/plan/approve")
async def approve(
    req: ApproveRequest,
    principal: Principal = Depends(get_principal),
) -> EventSourceResponse:
    decision = "approved" if req.decision.lower() in {"approved", "approve", "yes"} else "declined"
    audit("plan_approval", principal.user_id, decision=decision)

    graph = _get_graph()
    config = _thread(principal, req.thread_id)
    await graph.aupdate_state(config, {"approvals": {"reserve": decision}})
    return EventSourceResponse(_stream_run(graph, None, config))
