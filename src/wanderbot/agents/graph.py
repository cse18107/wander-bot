"""Supervisor graph assembly.

A central supervisor routes (deterministically) to specialist nodes; each
specialist returns to the supervisor, which re-decides. The budget<->replan loop
and the human-approval interrupt live here. State is checkpointed so the run can
pause (HITL) and resume on any replica.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from wanderbot.agents import routing
from wanderbot.agents.bundle import Deps, build_default_deps
from wanderbot.agents.nodes import Nodes
from wanderbot.agents.state import TripState

SUPERVISOR = "supervisor"

# Specialist node id -> always return to the supervisor to re-route.
_SPECIALISTS = [
    routing.INTAKE,
    routing.CLARIFY,
    routing.RESEARCH,
    routing.FLIGHTS,
    routing.SELECT_FLIGHT,
    routing.LODGING,
    routing.ACTIVITIES,
    routing.BUDGET,
    routing.REPLAN,
    routing.ITINERARY,
    routing.CURATE_IMAGES,
    routing.FINALIZE_LEG,
    routing.RESERVE,
    routing.RESPOND,
]

# Nodes that terminate the run after they speak (no further routing).
_TERMINAL = {routing.RESPOND, routing.RESERVE}


def build_graph(
    deps: Deps | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    deps = deps or build_default_deps()
    nodes = Nodes(deps)

    async def supervisor(state: TripState) -> TripState:
        return {"next": routing.decide_next(state)}

    def route(state: TripState) -> str:
        nxt = state.get("next") or routing.decide_next(state)
        return END if nxt == routing.END else nxt

    graph = StateGraph(TripState)
    graph.add_node(SUPERVISOR, supervisor)
    graph.add_node(routing.INTAKE, nodes.intake)
    graph.add_node(routing.CLARIFY, nodes.clarify)
    graph.add_node(routing.RESEARCH, nodes.research)
    graph.add_node(routing.FLIGHTS, nodes.flights)
    graph.add_node(routing.SELECT_FLIGHT, nodes.select_flight)
    graph.add_node(routing.LODGING, nodes.lodging)
    graph.add_node(routing.ACTIVITIES, nodes.activities)
    graph.add_node(routing.BUDGET, nodes.budget)
    graph.add_node(routing.REPLAN, nodes.replan)
    graph.add_node(routing.ITINERARY, nodes.itinerary)
    graph.add_node(routing.CURATE_IMAGES, nodes.curate_images)
    graph.add_node(routing.FINALIZE_LEG, nodes.finalize_leg)
    graph.add_node(routing.RESERVE, nodes.reserve)
    graph.add_node(routing.RESPOND, nodes.respond)

    graph.set_entry_point(SUPERVISOR)
    graph.add_conditional_edges(
        SUPERVISOR,
        route,
        {n: n for n in _SPECIALISTS} | {END: END},
    )
    # Specialists loop back to the supervisor, except terminal ones.
    for node in _SPECIALISTS:
        if node in _TERMINAL:
            graph.add_edge(node, END)
        else:
            graph.add_edge(node, SUPERVISOR)

    # Pause for: date clarification, flight selection, and reserve approval.
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=[routing.CLARIFY, routing.SELECT_FLIGHT, routing.RESERVE],
    )
