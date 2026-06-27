"""Swarm variant — decentralized handoffs (alternative to the supervisor).

Same specialists, but there is no central router node: each specialist computes
the next hop itself and hands off directly via ``Command(goto=...)``. This trades
the supervisor's central observability/accountability for lower latency (one fewer
hop per step). Provided as an alternate entrypoint to demonstrate the tradeoff
documented in DESIGN.md §6.4 / §16.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from wanderbot.agents import routing
from wanderbot.agents.bundle import Deps, build_default_deps
from wanderbot.agents.nodes import Nodes
from wanderbot.agents.state import TripState

NodeFn = Callable[[TripState], Awaitable[dict]]


def _handoff(node_fn: NodeFn) -> NodeFn:
    """Wrap a specialist so it applies its update then hands off to the next."""

    async def wrapped(state: TripState) -> Command:
        update = await node_fn(state)
        merged: TripState = {**state, **update}  # type: ignore[typeddict-item]
        goto = routing.decide_next(merged)
        return Command(goto=END if goto == routing.END else goto, update=update)

    return wrapped


def build_swarm_graph(
    deps: Deps | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    deps = deps or build_default_deps()
    n = Nodes(deps)

    graph = StateGraph(TripState)
    specialists: dict[str, NodeFn] = {
        routing.INTAKE: n.intake,
        routing.CLARIFY: n.clarify,
        routing.RESEARCH: n.research,
        routing.FLIGHTS: n.flights,
        routing.SELECT_FLIGHT: n.select_flight,
        routing.LODGING: n.lodging,
        routing.ACTIVITIES: n.activities,
        routing.BUDGET: n.budget,
        routing.REPLAN: n.replan,
        routing.ITINERARY: n.itinerary,
        routing.CURATE_IMAGES: n.curate_images,
        routing.RESERVE: n.reserve,
        routing.RESPOND: n.respond,
    }
    for name, fn in specialists.items():
        graph.add_node(name, _handoff(fn))

    graph.set_entry_point(routing.INTAKE)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=[routing.CLARIFY, routing.SELECT_FLIGHT, routing.RESERVE],
    )
