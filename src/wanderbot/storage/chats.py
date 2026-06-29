"""Chat threads: persisted conversations scoped per user + plan."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from wanderbot.storage import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_thread(user_id: str, plan_id: str) -> str:
    tid = uuid.uuid4().hex
    now = _now()
    await db.execute(
        "INSERT INTO chat_threads (id, user_id, plan_id, title, messages, created_at, updated_at) "
        "VALUES (:id, :uid, :pid, NULL, '[]', :now, :now)",
        {"id": tid, "uid": user_id, "pid": plan_id, "now": now},
    )
    return tid


async def list_threads(user_id: str, plan_id: str) -> list[dict[str, Any]]:
    return await db.fetch_all(
        "SELECT id, title, updated_at FROM chat_threads WHERE user_id = :uid AND plan_id = :pid "
        "ORDER BY updated_at DESC",
        {"uid": user_id, "pid": plan_id},
    )


async def get_thread(thread_id: str, user_id: str) -> dict[str, Any] | None:
    d = await db.fetch_one(
        "SELECT * FROM chat_threads WHERE id = :id AND user_id = :uid",
        {"id": thread_id, "uid": user_id},
    )
    if not d:
        return None
    d["messages"] = json.loads(d["messages"])
    return d


async def update_messages(thread_id: str, user_id: str, messages: list[dict[str, str]]) -> None:
    await db.execute(
        "UPDATE chat_threads SET messages = :msgs, updated_at = :now WHERE id = :id AND user_id = :uid",
        {"msgs": json.dumps(messages), "now": _now(), "id": thread_id, "uid": user_id},
    )


async def set_title(thread_id: str, user_id: str, title: str) -> None:
    await db.execute(
        "UPDATE chat_threads SET title = :title, updated_at = :now WHERE id = :id AND user_id = :uid",
        {"title": title, "now": _now(), "id": thread_id, "uid": user_id},
    )


async def delete_thread(thread_id: str, user_id: str) -> None:
    await db.execute(
        "DELETE FROM chat_threads WHERE id = :id AND user_id = :uid",
        {"id": thread_id, "uid": user_id},
    )
