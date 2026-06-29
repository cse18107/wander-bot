"""Saved plans, scoped per user, with a per-day detail cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from wanderbot.storage import db


async def upsert_plan(
    plan_id: str,
    user_id: str,
    title: str | None,
    destination: str | None,
    hero: str | None,
    data: dict[str, Any],
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO plans (id, user_id, title, destination, hero, data, created_at, updated_at)
        VALUES (:id, :user_id, :title, :destination, :hero, :data, :now, :now)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, destination=excluded.destination,
            hero=excluded.hero, data=excluded.data, updated_at=excluded.updated_at
        """,
        {"id": plan_id, "user_id": user_id, "title": title, "destination": destination,
         "hero": hero, "data": json.dumps(data), "now": now},
    )


async def list_plans(user_id: str) -> list[dict[str, Any]]:
    return await db.fetch_all(
        "SELECT id, title, destination, hero, updated_at FROM plans WHERE user_id = :uid "
        "ORDER BY updated_at DESC",
        {"uid": user_id},
    )


async def get_plan(plan_id: str, user_id: str) -> dict[str, Any] | None:
    d = await db.fetch_one(
        "SELECT * FROM plans WHERE id = :id AND user_id = :uid",
        {"id": plan_id, "uid": user_id},
    )
    if not d:
        return None
    d["data"] = json.loads(d["data"])
    return d


async def save_day_detail(plan_id: str, user_id: str, day: int, detail: dict[str, Any]) -> None:
    plan = await get_plan(plan_id, user_id)
    if not plan:
        return
    data = plan["data"]
    data.setdefault("day_details", {})[str(day)] = detail
    await upsert_plan(plan_id, user_id, plan["title"], plan["destination"], plan["hero"], data)


def plan_data_from_state(values: dict[str, Any], existing_details: dict | None = None) -> dict[str, Any] | None:
    """Serialize graph state values into a persistable plan record.

    Multi-stop trips carry a ``legs`` list (one finished plan per destination).
    The top-level fields mirror the FIRST leg so the plan list / hero stay stable
    while later legs are still being planned.
    """
    def dump(v):  # noqa: ANN001, ANN202
        return v.model_dump(mode="json") if v is not None and hasattr(v, "model_dump") else v

    legs = [dump(lp) for lp in (values.get("leg_plans") or [])]
    itin = values.get("itinerary")

    top_itin = (legs[0].get("itinerary") if legs else None) or dump(itin)
    if top_itin is None:
        return None

    return {
        "itinerary": top_itin,
        "selections": dump(values.get("selections")),
        "budget": (legs[0].get("budget") if legs else None) or dump(values.get("budget")),
        "brief": dump(values.get("brief")),
        "geo": dump(values.get("geo")),
        "images": (legs[0].get("images") if legs else None) or values.get("images") or [],
        "day_images": (legs[0].get("day_images") if legs else None) or values.get("day_images") or {},
        "legs": legs,
        "legs_complete": bool(values.get("legs_complete")),
        "day_details": existing_details or {},
    }
