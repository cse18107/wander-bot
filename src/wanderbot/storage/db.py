"""SQLite app store (users + saved plans) — zero-config, runs without Postgres.

A single shared aiosqlite connection (SQLite serializes writes) is fine for the
demo's concurrency. Schema is created on first use.
"""

from __future__ import annotations

import asyncio

import aiosqlite

from wanderbot.config import get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

_conn: aiosqlite.Connection | None = None
_loop: asyncio.AbstractEventLoop | None = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    home_city TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    destination TEXT,
    hero TEXT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_user ON plans(user_id);
CREATE TABLE IF NOT EXISTS chat_threads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    title TEXT,
    messages TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_user_plan ON chat_threads(user_id, plan_id);
"""


async def get_conn() -> aiosqlite.Connection:
    """Shared connection, recreated if the running event loop changed.

    aiosqlite binds a connection to the loop it was created on; tests (and any
    multi-loop context) need it recreated when the loop differs.
    """
    global _conn, _loop
    loop = asyncio.get_running_loop()
    if _conn is not None and _loop is not loop:
        try:
            await _conn.close()
        except Exception:
            pass
        _conn = None
    if _conn is None:
        path = get_settings().sqlite_path
        _conn = await aiosqlite.connect(path)
        _conn.row_factory = aiosqlite.Row
        await _conn.executescript(_SCHEMA)
        # Lightweight migration: add home_city to existing user tables.
        try:
            await _conn.execute("ALTER TABLE users ADD COLUMN home_city TEXT")
        except Exception:
            pass  # column already exists
        await _conn.commit()
        _loop = loop
        log.info("sqlite_ready", path=path)
    return _conn


async def init_db() -> None:
    await get_conn()


async def reset_conn() -> None:
    """Test hook: close the cached connection."""
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None
