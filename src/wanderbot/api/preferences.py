"""Preferences API — read and 'forget' a user's learned long-term memories."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from wanderbot.api.deps import get_principal
from wanderbot.memory.runtime import get_memory_store
from wanderbot.security.audit import audit
from wanderbot.security.auth import Principal

router = APIRouter(prefix="/api", tags=["preferences"])


class Preferences(BaseModel):
    items: list[str]


@router.get("/preferences", response_model=Preferences)
async def list_preferences(principal: Principal = Depends(get_principal)) -> Preferences:
    store = get_memory_store()
    items = await store.search(principal.user_id, "travel preferences", k=20)
    return Preferences(items=items)


@router.delete("/preferences")
async def forget_preferences(principal: Principal = Depends(get_principal)) -> dict[str, str]:
    # Privacy affordance: clear this user's namespace (in-memory backend).
    store = get_memory_store()
    data = getattr(store, "_data", None)
    if isinstance(data, dict):
        data.pop(principal.user_id, None)
    audit("preferences_forget", principal.user_id)
    return {"status": "cleared"}
