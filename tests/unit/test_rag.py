import pytest

from wanderbot.rag.knowledge_base import build_retriever, load_documents
from wanderbot.rag.research import Researcher
from wanderbot.rag.retriever import Document, HybridRetriever


@pytest.mark.asyncio
async def test_retriever_ranks_relevant_chunk_with_citation() -> None:
    docs = [
        Document(text="Japan is best in late October for food and hiking.", source="japan.md#0"),
        Document(text="Italy is best in May and September for wine.", source="italy.md#0"),
    ]
    retriever = HybridRetriever(docs)
    hits = await retriever.retrieve("Japan October hiking", k=2)
    assert hits
    assert hits[0].source.startswith("japan")
    assert hits[0].score > 0


@pytest.mark.asyncio
async def test_researcher_returns_notes_and_citations() -> None:
    retriever = build_retriever()  # loads the seed KB from data/kb
    researcher = Researcher(retriever, web=None)
    result = await researcher.research("Japan best time to visit food hiking")
    assert "October" in result.notes or "autumn" in result.notes
    assert any(c.startswith("japan.md") for c in result.citations)


def test_kb_loads_seed_documents() -> None:
    docs = load_documents()
    assert any(d.source.startswith("japan.md") for d in docs)
