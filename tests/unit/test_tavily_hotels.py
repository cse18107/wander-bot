from datetime import date

import pytest

from wanderbot.providers.tavily import TavilyProvider, TavilySearchResult


def test_tavily_image_parsing_handles_strings_and_objects() -> None:
    data = {
        "images": [
            "https://img.example/1.jpg",
            {"url": "https://img.example/2.jpg", "description": "Tower Bridge"},
            {"description": "no url, skipped"},
        ]
    }
    imgs = TavilyProvider._parse_images(data)
    assert [i.url for i in imgs] == ["https://img.example/1.jpg", "https://img.example/2.jpg"]
    assert imgs[1].description == "Tower Bridge"
from wanderbot.providers.tavily_hotels import TavilyHotelProvider, _HotelCandidate, _HotelCandidates


class _FakeTavily:
    async def search(self, query, max_results=5):
        return [
            TavilySearchResult(
                title="Best mid-range hotels in London",
                url="https://example.com/london-hotels",
                content="The Strand Palace is a solid mid-range pick around 640 GBP for a week.",
            )
        ]


class _FakeStructured:
    def __init__(self, value):
        self._value = value

    async def ainvoke(self, _):
        return self._value


class _FakeModel:
    def with_structured_output(self, schema):
        return _FakeStructured(
            _HotelCandidates(
                items=[
                    _HotelCandidate(
                        name="The Strand Palace", estimated_total_price=640.0,
                        currency="GBP", area="Covent Garden",
                    )
                ]
            )
        )


@pytest.mark.asyncio
async def test_tavily_hotels_extracts_named_hotels_with_estimates() -> None:
    provider = TavilyHotelProvider(_FakeTavily(), _FakeModel())
    offers = await provider.search_web_hotels(
        "London", date(2026, 8, 1), date(2026, 8, 8), adults=2, currency="GBP"
    )
    assert len(offers) == 1
    o = offers[0]
    assert "Strand Palace" in o.name
    assert "web est." in o.name  # clearly labeled as an estimate
    assert o.price.amount == 640.0
    assert o.price.currency == "GBP"
    assert o.bookable is False  # fallback suggestion -> UI renders inactive
    assert o.source == "web"
    assert o.note


@pytest.mark.asyncio
async def test_tavily_hotels_empty_when_no_results() -> None:
    class _Empty:
        async def search(self, q, max_results=5):
            return []

    provider = TavilyHotelProvider(_Empty(), _FakeModel())
    assert await provider.search_web_hotels("Nowhere", date(2026, 8, 1), date(2026, 8, 8)) == []
