from wanderbot.providers.duffel.flights import DuffelFlightProvider

SAMPLE = {
    "data": {
        "offers": [
            {
                "id": "off_123",
                "total_amount": "742.55",
                "total_currency": "USD",
                "slices": [
                    {
                        "segments": [
                            {
                                "origin": {"iata_code": "JFK"},
                                "destination": {"iata_code": "NRT"},
                                "departing_at": "2026-10-12T09:00:00",
                                "arriving_at": "2026-10-13T13:00:00",
                                "marketing_carrier": {"iata_code": "NH"},
                                "marketing_carrier_flight_number": "9",
                            }
                        ]
                    }
                ],
            }
        ]
    }
}


def test_parse_maps_duffel_offer_to_domain() -> None:
    offers = DuffelFlightProvider._parse(SAMPLE)
    assert len(offers) == 1
    o = offers[0]
    assert o.id == "off_123"
    assert o.origin == "JFK"
    assert o.destination == "NRT"
    assert o.price.amount == 742.55
    assert o.price.currency == "USD"
    assert o.stops == 0
    assert o.segments[0].carrier == "NH"


def test_parse_empty_is_safe() -> None:
    assert DuffelFlightProvider._parse({"data": {"offers": []}}) == []
    assert DuffelFlightProvider._parse({}) == []
