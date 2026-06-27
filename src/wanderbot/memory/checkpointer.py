"""Short-term memory: LangGraph checkpointer factory.

Postgres-backed in real deployments (durable conversations, HITL pause/resume,
time-travel). Falls back to an in-memory saver when no DB is configured so local
dev and unit tests need no infrastructure.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.base import BaseCheckpointSaver

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def open_checkpointer(
    settings: Settings | None = None,
) -> AsyncIterator[BaseCheckpointSaver]:
    settings = settings or get_settings()
    use_pg = settings.database_url.startswith("postgres") and settings.env != "local"
    if use_pg:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            async with AsyncPostgresSaver.from_conn_string(settings.database_url) as saver:
                await saver.setup()
                log.info("checkpointer", backend="postgres")
                yield saver
                return
        except Exception as exc:  # pragma: no cover - infra fallback
            log.warning("postgres_checkpointer_failed", error=str(exc))

    from langgraph.checkpoint.memory import MemorySaver

    log.info("checkpointer", backend="memory")
    yield MemorySaver()
