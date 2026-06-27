"""The swarm variant should reach the same plan via decentralized handoffs."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from wanderbot.agents import routing
from wanderbot.agents.bundle import Deps
from wanderbot.agents.state import initial_state
from wanderbot.agents.swarm import build_swarm_graph
from tests.agents.doubles import (
    FakeActivities,
    FakeFlights,
    FakeGeo,
    FakeHotels,
    FakeModel,
    run_until_reserve,
    sample_brief,
)


@pytest.mark.asyncio
async def test_swarm_reaches_itinerary_and_pauses_for_approval() -> None:
    deps = Deps(
        model=FakeModel(sample_brief()),
        flights=FakeFlights(),
        hotels=FakeHotels(),
        activities=FakeActivities(),
        geo=FakeGeo(),
    )
    graph = build_swarm_graph(deps=deps, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "s1"}}

    # The swarm reaches the flight-selection pause via decentralized handoffs.
    await graph.ainvoke(initial_state(HumanMessage(content="plan Tokyo")), config)
    snapshot = await graph.aget_state(config)
    assert snapshot.next == (routing.SELECT_FLIGHT,)
    assert snapshot.values.get("flight_options")
