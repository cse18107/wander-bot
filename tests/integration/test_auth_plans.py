"""Auth + per-user plan persistence + day-detail caching."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wanderbot.api.main import create_app
from wanderbot.storage.db import reset_conn
from wanderbot.storage.plans import get_plan, save_day_detail, upsert_plan

client = TestClient(create_app())


def test_register_login_and_isolation() -> None:
    r = client.post("/api/auth/register", json={"email": "a@x.com", "password": "secret1"})
    assert r.status_code == 200
    token_a = r.json()["token"]

    # duplicate email rejected
    assert client.post("/api/auth/register", json={"email": "a@x.com", "password": "secret1"}).status_code == 400
    # wrong password
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "nope"}).status_code == 401
    # correct login
    assert client.post("/api/auth/login", json={"email": "a@x.com", "password": "secret1"}).status_code == 200

    # a second user
    token_b = client.post("/api/auth/register", json={"email": "b@x.com", "password": "secret1"}).json()["token"]
    assert token_a != token_b


@pytest.mark.asyncio
async def test_plans_are_per_user_and_day_detail_caches() -> None:
    await reset_conn()
    await upsert_plan(
        "plan-1", "user-1", "Tokyo Trip", "Tokyo", "hero.jpg",
        {"itinerary": {"summary": "x", "days": [{"day": 1, "title": "Arrival", "items": ["a"]}]}},
    )
    await upsert_plan("plan-2", "user-2", "Rome Trip", "Rome", None, {"itinerary": {"summary": "y", "days": []}})

    from wanderbot.storage.plans import list_plans

    u1 = await list_plans("user-1")
    assert len(u1) == 1 and u1[0]["destination"] == "Tokyo"
    assert await get_plan("plan-1", "user-2") is None  # isolation

    # day-detail cache write + read
    await save_day_detail("plan-1", "user-1", 1, {"day": 1, "title": "Arrival", "weather": "Mild"})
    plan = await get_plan("plan-1", "user-1")
    assert plan["data"]["day_details"]["1"]["weather"] == "Mild"
