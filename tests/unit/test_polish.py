from datetime import date

from wanderbot.agents.state import Selections
from wanderbot.domain import FlightOffer, FlightSegment, Money
from wanderbot.memory.serde import build_serde
from wanderbot.providers.duffel.stays import DuffelStaysProvider


def _flight(currency: str) -> FlightOffer:
    return FlightOffer(
        id="F1",
        price=Money(amount=821, currency=currency),
        segments=[
            FlightSegment(origin="JFK", destination="LHR", departure_at="x", arrival_at="y",
                          carrier="BA", flight_number="105")
        ],
        stops=0,
    )


def test_selection_currency_follows_flight() -> None:
    sel = Selections(flight=_flight("GBP"))
    assert sel.currency("USD") == "GBP"
    assert Selections().currency("USD") == "USD"  # default when nothing priced


def test_duffel_stays_parse() -> None:
    payload = {
        "data": {
            "results": [
                {
                    "id": "stay_1",
                    "accommodation": {"name": "The Strand Hotel", "rating": 4},
                    "cheapest_rate_total_amount": "640.00",
                    "cheapest_rate_currency": "GBP",
                }
            ]
        }
    }
    hotels = DuffelStaysProvider._parse(payload, date(2026, 8, 1), date(2026, 8, 8))
    assert len(hotels) == 1
    assert hotels[0].name == "The Strand Hotel"
    assert hotels[0].price.amount == 640.0
    assert hotels[0].price.currency == "GBP"
    assert hotels[0].rating == "4"


def test_checkpoint_serde_roundtrips_state_types() -> None:
    serde = build_serde()
    sel = Selections(flight=_flight("GBP"))
    restored = serde.loads_typed(serde.dumps_typed(sel))
    assert restored.flight is not None
    assert restored.flight.price.currency == "GBP"
