from wanderbot.providers.amadeus.flights import AmadeusFlightProvider

SAMPLE = {
    "data": [
        {
            "id": "1",
            "price": {"grandTotal": "812.30", "currency": "USD"},
            "itineraries": [
                {
                    "duration": "PT14H",
                    "segments": [
                        {
                            "departure": {"iataCode": "JFK", "at": "2026-10-12T09:00:00"},
                            "arrival": {"iataCode": "NRT", "at": "2026-10-13T13:00:00"},
                            "carrierCode": "NH",
                            "number": "9",
                        }
                    ],
                }
            ],
        }
    ]
}


def test_parse_maps_vendor_json_to_domain() -> None:
    offers = AmadeusFlightProvider._parse(SAMPLE)
    assert len(offers) == 1
    o = offers[0]
    assert o.origin == "JFK"
    assert o.destination == "NRT"
    assert o.price.amount == 812.30
    assert o.price.currency == "USD"
    assert o.stops == 0
    assert o.segments[0].carrier == "NH"


def test_parse_empty_is_safe() -> None:
    assert AmadeusFlightProvider._parse({}) == []
