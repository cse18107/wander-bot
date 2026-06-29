"""App store (users + saved plans + chat threads) via SQLAlchemy async.

One code path serves both backends:
- **dev**: SQLite (zero-config) when ``WB_APP_STORE_URL`` is unset.
- **prod**: Postgres when ``WB_APP_STORE_URL`` is a ``postgresql://`` URL — required
  because the API container runs with a read-only root filesystem (SQLite can't
  write there).

Queries use named (``:param``) binds, which work identically on both engines, and
the ``ON CONFLICT(id) DO UPDATE`` upsert is supported by SQLite 3.24+ and Postgres.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from wanderbot.config import get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_engine: AsyncEngine | None = None

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        pw_hash TEXT NOT NULL,
        home_city TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS plans (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        title TEXT,
        destination TEXT,
        hero TEXT,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_plans_user ON plans(user_id)",
    """
    CREATE TABLE IF NOT EXISTS chat_threads (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        plan_id TEXT NOT NULL,
        title TEXT,
        messages TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_threads_user_plan ON chat_threads(user_id, plan_id)",
]


def _engine_url() -> str:
    s = get_settings()
    if s.app_store_url:
        url = s.app_store_url
        # Normalize to the async driver SQLAlchemy expects.
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url
    return f"sqlite+aiosqlite:///{s.sqlite_path}"


async def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = _engine_url()
        # NullPool for SQLite avoids connections being pinned to one event loop
        # (matters for tests that spin up a loop per test); Postgres keeps a pool.
        kwargs: dict[str, Any] = {"future": True}
        if url.startswith("sqlite"):
            kwargs["poolclass"] = NullPool
        else:
            kwargs["pool_pre_ping"] = True
        _engine = create_async_engine(url, **kwargs)
        async with _engine.begin() as conn:
            for stmt in _SCHEMA:
                await conn.execute(text(stmt))
            # Legacy migration for older SQLite files missing home_city.
            try:
                await conn.execute(text("ALTER TABLE users ADD COLUMN home_city TEXT"))
            except Exception:
                pass  # column already exists / Postgres fresh schema
        log.info("app_store_ready", backend="postgres" if "postgresql" in url else "sqlite")
    return _engine


# --- small query helpers (named :params work on both backends) ---------------
async def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    engine = await get_engine()
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), params or {})).mappings().first()
        return dict(row) if row else None


async def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    engine = await get_engine()
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params or {})).mappings().all()
        return [dict(r) for r in rows]


async def execute(sql: str, params: dict[str, Any] | None = None) -> None:
    engine = await get_engine()
    async with engine.begin() as conn:
        await conn.execute(text(sql), params or {})


async def init_db() -> None:
    await get_engine()


async def reset_conn() -> None:
    """Test hook: dispose the cached engine so the next call rebuilds it."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
