"""Long-term memory store (cross-conversation, per-user).

Two backends behind one interface:
- ``InMemoryStore``: zero-infra, used for local/dev/tests. Does vector search when
  an embedder is supplied, otherwise a lexical (token-overlap) fallback.
- ``PostgresVectorStore``: pgvector-backed for production (durable, multi-user,
  semantic search). Memories are namespaced per ``user_id`` and never cross tenants.
"""

from __future__ import annotations

import math
import uuid
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

Embedder = "EmbedderProto"


@runtime_checkable
class EmbedderProto(Protocol):
    async def aembed(self, texts: list[str]) -> list[list[float]]: ...


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_id: str
    kind: str = "preference"  # preference | trajectory
    text: str
    embedding: list[float] | None = None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _lexical(query: str, text: str) -> float:
    q = set(query.lower().split())
    t = set(text.lower().split())
    if not q or not t:
        return 0.0
    return len(q & t) / len(q | t)


@runtime_checkable
class LongTermMemory(Protocol):
    async def add(self, user_id: str, text: str, kind: str = "preference") -> None: ...
    async def search(self, user_id: str, query: str, k: int = 5) -> list[str]: ...


class InMemoryStore:
    def __init__(self, embedder: EmbedderProto | None = None):
        self._data: dict[str, list[MemoryRecord]] = {}
        self._embedder = embedder

    async def add(self, user_id: str, text: str, kind: str = "preference") -> None:
        emb = None
        if self._embedder is not None:
            emb = (await self._embedder.aembed([text]))[0]
        rec = MemoryRecord(user_id=user_id, text=text, kind=kind, embedding=emb)
        self._data.setdefault(user_id, []).append(rec)

    async def search(self, user_id: str, query: str, k: int = 5) -> list[str]:
        records = self._data.get(user_id, [])
        if not records:
            return []
        if self._embedder is not None:
            qv = (await self._embedder.aembed([query]))[0]
            scored = [
                (_cosine(qv, r.embedding or []), r.text) for r in records if r.embedding
            ]
        else:
            scored = [(_lexical(query, r.text), r.text) for r in records]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for score, text in scored[:k] if score > 0]
