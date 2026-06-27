"""Process-wide long-term memory singleton.

In production this is the pgvector store; for local/dev it's the in-memory store.
Shared by the graph (writes) and the preferences API (reads/forget).
"""

from __future__ import annotations

from wanderbot.config import get_settings
from wanderbot.memory.store import InMemoryStore, LongTermMemory
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_store: LongTermMemory | None = None


def get_memory_store() -> LongTermMemory:
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.database_url.startswith("postgres") and settings.env != "local":
        try:
            from wanderbot.llm_factory import build_embeddings
            from wanderbot.memory.pgvector_store import PostgresVectorStore

            class _Embedder:
                def __init__(self):
                    self._e = build_embeddings()

                async def aembed(self, texts: list[str]) -> list[list[float]]:
                    return await self._e.aembed_documents(texts)

            _store = PostgresVectorStore(settings.database_url, _Embedder())  # type: ignore[assignment]
            log.info("memory_store", backend="pgvector")
            return _store
        except Exception as exc:  # pragma: no cover - fallback
            log.warning("pgvector_unavailable", error=str(exc))
    _store = InMemoryStore()
    log.info("memory_store", backend="memory")
    return _store
