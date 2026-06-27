"""Preference extraction + procedural memory.

After a trip, distill durable user preferences from the conversation and persist
them. On a new trip, relevant memories are retrieved and injected into the brief.
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from wanderbot.memory.store import LongTermMemory
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)


class ExtractedPreferences(BaseModel):
    items: list[str] = Field(
        default_factory=list,
        description="Durable, reusable traveler preferences, e.g. 'prefers aisle seats'",
    )


async def extract_and_store(
    model: BaseChatModel,
    memory: LongTermMemory,
    user_id: str,
    conversation: str,
) -> list[str]:
    structured = model.with_structured_output(ExtractedPreferences)
    prompt = (
        "Extract durable, reusable travel preferences from this conversation. "
        "Only stable facts useful for future trips (seat/food/hotel tier/pace), "
        "not one-off details.\n\n" + conversation
    )
    result: ExtractedPreferences = await structured.ainvoke(prompt)  # type: ignore[assignment]
    for item in result.items:
        await memory.add(user_id, item, kind="preference")
    log.info("preferences_stored", user_id=user_id, count=len(result.items))
    return result.items


async def recall(memory: LongTermMemory, user_id: str, query: str, k: int = 5) -> list[str]:
    return await memory.search(user_id, query, k=k)
