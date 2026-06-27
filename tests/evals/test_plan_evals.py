"""Rule-based plan evals (deterministic, gate-able in CI).

These assert hard constraints on the produced plan: budget adherence, a non-empty
itinerary, and that selections were made. LLM-as-judge quality evals (tone,
geographic coherence) run separately against a LangSmith dataset when an API key
is present — out of scope for the offline gate.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from wanderbot.agents.bundle import Deps
from wanderbot.agents.graph import build_graph
from wanderbot.agents.state import initial_state
from tests.agents.doubles import (
    FakeActivities,
    FakeFlights,
    FakeGeo,
    FakeHotels,
    FakeModel,
    run_until_reserve,
    sample_brief,
)


def _run_config():
    return {"configurable": {"thread_id": "eval"}}


@pytest.mark.asyncio
async def test_plan_respects_budget_constraint() -> None:
    deps = Deps(
        model=FakeModel(sample_brief(budget_total=500)),
        flights=FakeFlights(price=300.0),
        hotels=FakeHotels(price=100.0),
        activities=FakeActivities(prices=[150.0, 150.0, 150.0]),
        geo=FakeGeo(),
    )
    graph = build_graph(deps=deps, checkpointer=MemorySaver())
    result = await run_until_reserve(graph, _run_config(), initial_state(HumanMessage(content="cheap trip")))

    # Hard constraint: final total within the stated budget.
    assert result["budget"].total <= 500
    # Itinerary produced with at least one day.
    assert result["itinerary"] is not None
    assert len(result["itinerary"].days) >= 1
    # Core selections were actually made from real-shaped data.
    assert result["selections"].flight is not None
    assert result["selections"].hotel is not None


@pytest.mark.asyncio
async def test_plan_handles_unconstrained_budget() -> None:
    deps = Deps(
        model=FakeModel(sample_brief(budget_total=None)),
        flights=FakeFlights(),
        hotels=FakeHotels(),
        activities=FakeActivities(),
        geo=FakeGeo(),
    )
    graph = build_graph(deps=deps, checkpointer=MemorySaver())
    result = await run_until_reserve(graph, _run_config(), initial_state(HumanMessage(content="plan it")))
    assert result["budget"].status == "ok"
    assert result["iterations"] == 0  # no replan needed
