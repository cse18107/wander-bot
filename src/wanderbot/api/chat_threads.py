"""Chat threads API: multiple conversations per trip, with LLM-titled history."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from wanderbot.api.deps import get_principal
from wanderbot.api.plan import _message_text, run_trip_agent
from wanderbot.observability.logging import get_logger
from wanderbot.security.auth import Principal
from wanderbot.storage import chats
from wanderbot.storage.plans import get_plan

log = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat-threads"])


class NewThread(BaseModel):
    plan_id: str


class Message(BaseModel):
    question: str


async def _generate_title(question: str) -> str:
    from langchain_core.messages import HumanMessage

    from wanderbot.llm_factory import build_chat_model

    try:
        resp = await build_chat_model(temperature=0.3).ainvoke(
            [
                HumanMessage(
                    content=(
                        "Write a very short chat title (3-5 words, no quotes, Title Case) for a "
                        f"trip-assistant conversation that begins with this message:\n\"{question}\""
                    )
                )
            ]
        )
        title = _message_text(resp).strip().strip('"').strip()
        return title[:60] or "New chat"
    except Exception:  # pragma: no cover
        return question[:40] or "New chat"


@router.post("/threads")
async def create_thread(body: NewThread, principal: Principal = Depends(get_principal)) -> dict[str, str]:
    tid = await chats.create_thread(principal.user_id, body.plan_id)
    return {"id": tid}


@router.get("/threads")
async def list_threads(plan_id: str, principal: Principal = Depends(get_principal)) -> list[dict[str, Any]]:
    return await chats.list_threads(principal.user_id, plan_id)


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, principal: Principal = Depends(get_principal)) -> dict[str, Any]:
    thread = await chats.get_thread(thread_id, principal.user_id)
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    return {"id": thread["id"], "title": thread["title"], "messages": thread["messages"]}


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, principal: Principal = Depends(get_principal)) -> dict[str, str]:
    await chats.delete_thread(thread_id, principal.user_id)
    return {"status": "deleted"}


@router.post("/threads/{thread_id}/message")
async def post_message(
    thread_id: str, body: Message, principal: Principal = Depends(get_principal)
) -> dict[str, Any]:
    thread = await chats.get_thread(thread_id, principal.user_id)
    if thread is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    plan = await get_plan(thread["plan_id"], principal.user_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "plan not found")

    history = thread["messages"]
    result = await run_trip_agent(plan, principal, body.question, history)

    assistant_msg: dict[str, Any] = {"role": "assistant", "text": result["answer"]}
    if result.get("cards"):
        assistant_msg["cards"] = result["cards"]
    new_messages = history + [{"role": "user", "text": body.question}, assistant_msg]
    await chats.update_messages(thread_id, principal.user_id, new_messages)

    # First exchange -> generate a title for the thread.
    new_title = None
    if not thread.get("title"):
        new_title = await _generate_title(body.question)
        await chats.set_title(thread_id, principal.user_id, new_title)

    return {
        "answer": result["answer"],
        "plan": result["plan"],
        "cards": result.get("cards"),
        "title": new_title,
    }
