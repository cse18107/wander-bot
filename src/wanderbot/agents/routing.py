"""Deterministic supervisor routing.

A senior tradeoff: the *happy path and the budget loop are a known state machine*,
so they're routed deterministically (robust, testable, cheap) rather than burning
an LLM call per hop. The LLM is used where judgment is needed — intake parsing,
itinerary authoring, and (optionally) an LLM router variant for open-ended dialog.
"""

from __future__ import annotations

from wanderbot.agents.state import TripState
from wanderbot.config import get_settings

# Node names (also graph node ids).
INTAKE = "intake"
CLARIFY = "clarify"
RESEARCH = "research"
FLIGHTS = "flights"
SELECT_FLIGHT = "select_flight"
LODGING = "lodging"
ACTIVITIES = "activities"
BUDGET = "budget"
REPLAN = "replan"
ITINERARY = "itinerary"
CURATE_IMAGES = "curate_images"
FINALIZE_LEG = "finalize_leg"
RESERVE = "reserve"
RESPOND = "respond"
END = "__end__"


def decide_next(state: TripState) -> str:
    brief = state.get("brief")
    if brief is None:
        return INTAKE
    if not brief.destination_city:
        return RESPOND  # can't plan without a destination
    if not brief.origin_city:
        return CLARIFY  # ask where the user is flying from (HITL)
    if not brief.start_date:
        return CLARIFY  # ask the user for a start date (HITL)

    if state.get("research") is None:
        return RESEARCH

    # Use per-step "done" flags (not result presence) so a step that legitimately
    # returns nothing — e.g. no hotel found — advances instead of looping forever.
    done = state.get("done", {})
    if not state.get("flights_searched"):
        return FLIGHTS  # search flights for the date
    if not done.get(FLIGHTS):
        return SELECT_FLIGHT  # pause for the user to pick (or proceed/change date)
    if not done.get(LODGING):
        return LODGING
    if not done.get(ACTIVITIES):
        return ACTIVITIES

    budget = state.get("budget")
    assert budget is not None
    if budget.status == "unknown":
        return BUDGET

    max_iter = get_settings().max_graph_iterations
    if budget.status == "over" and state.get("iterations", 0) < max_iter:
        return REPLAN

    if state.get("itinerary") is None:
        return ITINERARY

    # Itinerary ready -> curate per-day imagery.
    if not done.get("images"):
        return CURATE_IMAGES

    # This leg is fully planned. Package it (and loop to the next leg if any).
    if not state.get("legs_complete"):
        return FINALIZE_LEG

    # All legs done -> human approval, then end.
    if state.get("approvals", {}).get("reserve") != "approved":
        return RESERVE
    return END
