"""Chat thread persistence: create, list, messages, title, isolation, delete."""

from __future__ import annotations

import pytest

from wanderbot.storage import chats
from wanderbot.storage.db import reset_conn


@pytest.mark.asyncio
async def test_thread_lifecycle_and_isolation() -> None:
    await reset_conn()
    t1 = await chats.create_thread("user-1", "plan-1")
    t2 = await chats.create_thread("user-1", "plan-1")
    await chats.create_thread("user-2", "plan-1")  # other user

    # listing is scoped to user + plan
    listed = await chats.list_threads("user-1", "plan-1")
    assert {r["id"] for r in listed} == {t1, t2}

    # messages + title
    await chats.update_messages(t1, "user-1", [{"role": "user", "text": "hi"}])
    await chats.set_title(t1, "user-1", "Packing Tips")
    thread = await chats.get_thread(t1, "user-1")
    assert thread["title"] == "Packing Tips"
    assert thread["messages"][0]["text"] == "hi"

    # cross-user access denied
    assert await chats.get_thread(t1, "user-2") is None

    # delete
    await chats.delete_thread(t1, "user-1")
    assert await chats.get_thread(t1, "user-1") is None
