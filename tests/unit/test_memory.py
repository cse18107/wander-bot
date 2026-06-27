import pytest

from wanderbot.memory.preferences import extract_and_store
from wanderbot.memory.store import InMemoryStore


class _FakeStructured:
    def __init__(self, value):
        self._value = value

    async def ainvoke(self, _):
        return self._value


class _FakePrefModel:
    def __init__(self, items):
        from wanderbot.memory.preferences import ExtractedPreferences

        self._value = ExtractedPreferences(items=items)

    def with_structured_output(self, schema):
        return _FakeStructured(self._value)


@pytest.mark.asyncio
async def test_inmemory_store_is_per_user_and_searchable() -> None:
    store = InMemoryStore()
    await store.add("u1", "prefers aisle seats")
    await store.add("u1", "vegetarian meals please")
    await store.add("u2", "loves window seats")

    hits = await store.search("u1", "seat preference aisle", k=5)
    assert any("aisle" in h for h in hits)
    # tenant isolation
    assert all("window" not in h for h in hits)


@pytest.mark.asyncio
async def test_extract_and_store_persists_preferences() -> None:
    store = InMemoryStore()
    model = _FakePrefModel(["prefers aisle seats", "mid-range hotels"])
    items = await extract_and_store(model, store, "u1", "conversation text")
    assert items == ["prefers aisle seats", "mid-range hotels"]
    # Lexical fallback (no embedder) needs token overlap; prod uses embeddings.
    recalled = await store.search("u1", "mid-range hotels", k=5)
    assert any("mid-range" in r for r in recalled)
