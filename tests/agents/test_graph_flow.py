"""End-to-end graph behavior with injected fakes (deterministic, no network/LLM)."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from wanderbot.agents import routing
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


def _deps(budget_total=None, activity_prices=None, flight=600.0, hotel=400.0) -> Deps:
    return Deps(
        model=FakeModel(sample_brief(budget_total=budget_total)),
        flights=FakeFlights(price=flight),
        hotels=FakeHotels(price=hotel),
        activities=FakeActivities(prices=activity_prices),
        geo=FakeGeo(),
    )


@pytest.mark.asyncio
async def test_full_plan_pauses_at_human_approval() -> None:
    graph = build_graph(deps=_deps(), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t1"}}

    result = await run_until_reserve(graph, config, initial_state(HumanMessage(content="plan Tokyo")))

    # Itinerary built; the run is paused *before* the reserve node (HITL gate).
    assert result["itinerary"] is not None
    assert result["selections"].flight is not None
    assert result["selections"].hotel is not None
    snapshot = await graph.aget_state(config)
    assert snapshot.next == (routing.RESERVE,)


@pytest.mark.asyncio
async def test_resume_after_approval_records_decision() -> None:
    graph = build_graph(deps=_deps(), checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t2"}}
    await run_until_reserve(graph, config, initial_state(HumanMessage(content="plan Tokyo")))

    # Human approves, then we resume the paused run.
    await graph.aupdate_state(config, {"approvals": {"reserve": "approved"}})
    final = await graph.ainvoke(None, config)
    assert final["approvals"]["reserve"] == "approved"


@pytest.mark.asyncio
async def test_budget_loop_trims_activities_until_within_target() -> None:
    # flight 300 + hotel 100 = 400 base; activities 150+150 push to 700 > 500.
    deps = _deps(budget_total=500, activity_prices=[150.0, 150.0], flight=300.0, hotel=100.0)
    graph = build_graph(deps=deps, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t3"}}

    result = await run_until_reserve(graph, config, initial_state(HumanMessage(content="cheap Tokyo")))

    # At least one activity trimmed and final total within budget.
    assert result["iterations"] >= 1
    assert result["budget"].total <= 500
    assert result["itinerary"] is not None
