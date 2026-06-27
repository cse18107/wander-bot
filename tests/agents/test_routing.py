from wanderbot.agents import routing
from wanderbot.agents.state import BudgetState, Selections, initial_state
from wanderbot.domain import FlightOffer, FlightSegment, HotelOffer, Money
from langchain_core.messages import HumanMessage

from tests.agents.doubles import sample_brief


def _seg() -> FlightSegment:
    return FlightSegment(
        origin="JFK", destination="NRT", departure_at="x", arrival_at="y",
        carrier="NH", flight_number="9",
    )


def test_router_walks_the_happy_path() -> None:
    state = initial_state(HumanMessage(content="plan a trip"))
    assert routing.decide_next(state) == routing.INTAKE

    state["brief"] = sample_brief()
    assert routing.decide_next(state) == routing.RESEARCH

    state["research"] = "note"
    # Flights are searched, then the user selects one (HITL), then per-step flags.
    assert routing.decide_next(state) == routing.FLIGHTS

    state["flights_searched"] = True
    assert routing.decide_next(state) == routing.SELECT_FLIGHT

    state["done"] = {"flights": True}
    assert routing.decide_next(state) == routing.LODGING

    state["done"] = {"flights": True, "lodging": True}
    assert routing.decide_next(state) == routing.ACTIVITIES

    state["done"] = {"flights": True, "lodging": True, "activities": True}
    assert routing.decide_next(state) == routing.BUDGET


def test_router_sends_over_budget_to_replan() -> None:
    state = initial_state(HumanMessage(content="x"))
    state["brief"] = sample_brief(budget_total=500)
    state["research"] = "note"
    state["flights_searched"] = True
    state["done"] = {"flights": True, "lodging": True, "activities": True}
    state["selections"] = Selections(
        flight=FlightOffer(id="F1", price=Money(amount=600, currency="USD"), segments=[_seg()], stops=0),
        hotel=HotelOffer(id="H1", name="h", price=Money(amount=400, currency="USD"), check_in="a", check_out="b"),
        activities=[],
    )
    state["budget"] = BudgetState(target=500, status="over")
    state["iterations"] = 1
    assert routing.decide_next(state) == routing.REPLAN


def test_router_requests_info_when_not_searchable() -> None:
    state = initial_state(HumanMessage(content="x"))
    state["brief"] = sample_brief()
    state["brief"].destination_city = None
    assert routing.decide_next(state) == routing.RESPOND


def test_router_asks_for_start_date_when_missing() -> None:
    state = initial_state(HumanMessage(content="x"))
    brief = sample_brief()
    brief.start_date = None  # destination known, no start date -> clarify
    state["brief"] = brief
    assert routing.decide_next(state) == routing.CLARIFY
