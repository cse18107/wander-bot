"""Saved plans, scoped per user, with a per-day detail cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from wanderbot.storage.db import get_conn


async def upsert_plan(
    plan_id: str,
    user_id: str,
    title: str | None,
    destination: str | None,
    hero: str | None,
    data: dict[str, Any],
) -> None:
    conn = await get_conn()
    now = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        """
        INSERT INTO plans (id, user_id, title, destination, hero, data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title, destination=excluded.destination,
            hero=excluded.hero, data=excluded.data, updated_at=excluded.updated_at
        """,
        (plan_id, user_id, title, destination, hero, json.dumps(data), now, now),
    )
    await conn.commit()


async def list_plans(user_id: str) -> list[dict[str, Any]]:
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT id, title, destination, hero, updated_at FROM plans WHERE user_id = ? "
        "ORDER BY updated_at DESC",
        (user_id,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def get_plan(plan_id: str, user_id: str) -> dict[str, Any] | None:
    conn = await get_conn()
    cur = await conn.execute(
        "SELECT * FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
    )
    row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
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
    """Serialize graph state values into a persistable plan record."""
    itin = values.get("itinerary")
    if itin is None:
        return None

    def dump(v):  # noqa: ANN001, ANN202
        return v.model_dump(mode="json") if v is not None and hasattr(v, "model_dump") else v

    return {
        "itinerary": dump(itin),
        "selections": dump(values.get("selections")),
        "budget": dump(values.get("budget")),
        "brief": dump(values.get("brief")),
        "geo": dump(values.get("geo")),
        "images": values.get("images") or [],
        "day_images": values.get("day_images") or {},
        "day_details": existing_details or {},
    }
