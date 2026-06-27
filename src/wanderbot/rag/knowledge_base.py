"""Knowledge-base ingestion for the destination RAG corpus."""

from __future__ import annotations

from pathlib import Path

from wanderbot.memory.store import EmbedderProto
from wanderbot.rag.retriever import Document, HybridRetriever

_DEFAULT_KB = Path(__file__).resolve().parents[3] / "data" / "kb"


def load_documents(kb_dir: Path | None = None) -> list[Document]:
    kb_dir = kb_dir or _DEFAULT_KB
    docs: list[Document] = []
    if not kb_dir.exists():
        return docs
    for path in sorted(kb_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        # Chunk by paragraph to keep retrieval granular and citations precise.
        for i, chunk in enumerate(c.strip() for c in text.split("\n\n")):
            if chunk:
                docs.append(Document(text=chunk, source=f"{path.name}#{i}"))
    return docs


def build_retriever(
    kb_dir: Path | None = None, embedder: EmbedderProto | None = None
) -> HybridRetriever:
    return HybridRetriever(load_documents(kb_dir), embedder=embedder)
