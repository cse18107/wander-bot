"""Chat threads: persisted conversations scoped per user + plan."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from wanderbot.storage.db import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_thread(user_id: str, plan_id: str) -> str:
    conn = await get_conn()
    tid = uuid.uuid4().hex
    now = _now()
    await conn.execute(
        "INSERT INTO chat_threads (id, user_id, plan_id, title, messages, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (tid, user_id, plan_id, None, "[]", now, now),
    )
    await conn.commit()
    return tid


async def list_threads(user_id: str, plan_id: str) -> list[dict[str, Any]]:
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT id, title, updated_at FROM chat_threads WHERE user_id = ? AND plan_id = ? "
        "ORDER BY updated_at DESC",
        (user_id, plan_id),
    )
    return [dict(r) for r in await cur.fetchall()]


async def get_thread(thread_id: str, user_id: str) -> dict[str, Any] | None:
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM chat_threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
    )
    row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    d["messages"] = json.loads(d["messages"])
    return d


async def update_messages(thread_id: str, user_id: str, messages: list[dict[str, str]]) -> None:
    conn = await get_conn()
    await conn.execute(
        "UPDATE chat_threads SET messages = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (json.dumps(messages), _now(), thread_id, user_id),
    )
    await conn.commit()


async def set_title(thread_id: str, user_id: str, title: str) -> None:
    conn = await get_conn()
    await conn.execute(
        "UPDATE chat_threads SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (title, _now(), thread_id, user_id),
    )
    await conn.commit()


async def delete_thread(thread_id: str, user_id: str) -> None:
    conn = await get_conn()
    await conn.execute(
        "DELETE FROM chat_threads WHERE id = ? AND user_id = ?", (thread_id, user_id)
    )
    await conn.commit()
