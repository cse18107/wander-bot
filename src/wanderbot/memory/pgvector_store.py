"""Production long-term memory backend: Postgres + pgvector.

Real semantic search over per-user namespaced memories. Used when a database is
configured; otherwise the app falls back to ``InMemoryStore``.
"""

from __future__ import annotations

from wanderbot.memory.store import EmbedderProto
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_DIM = 1536  # text-embedding-3-small


class PostgresVectorStore:
    def __init__(self, dsn: str, embedder: EmbedderProto):
        self._dsn = dsn
        self._embedder = embedder

    async def setup(self) -> None:
        import psycopg

        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS user_memories (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'preference',
                    text TEXT NOT NULL,
                    embedding vector({_DIM}),
                    created_at TIMESTAMPTZ DEFAULT now()
                )
                """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id)"
            )
            await conn.commit()

    async def add(self, user_id: str, text: str, kind: str = "preference") -> None:
        import psycopg

        emb = (await self._embedder.aembed([text]))[0]
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            await conn.execute(
                "INSERT INTO user_memories (user_id, kind, text, embedding) VALUES (%s, %s, %s, %s)",
                (user_id, kind, text, str(emb)),
            )
            await conn.commit()

    async def search(self, user_id: str, query: str, k: int = 5) -> list[str]:
        import psycopg

        qv = (await self._embedder.aembed([query]))[0]
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            cur = await conn.execute(
                """
                SELECT text FROM user_memories
                WHERE user_id = %s
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (user_id, str(qv), k),
            )
            rows = await cur.fetchall()
        return [r[0] for r in rows]
