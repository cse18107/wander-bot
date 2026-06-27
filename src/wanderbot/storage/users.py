"""User accounts: create + authenticate (PBKDF2 password hashing, stdlib only)."""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone

from wanderbot.storage.db import get_conn

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _ITERATIONS)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


async def create_user(email: str, password: str, home_city: str | None = None) -> str:
    email = email.strip().lower()
    if not email or "@" not in email or len(password) < 6:
        raise ValueError("invalid email or password too short (min 6)")
    conn = await get_conn()
    cur = await conn.execute("SELECT id FROM users WHERE email = ?", (email,))
    if await cur.fetchone():
        raise ValueError("email already registered")
    uid = uuid.uuid4().hex
    await conn.execute(
        "INSERT INTO users (id, email, pw_hash, home_city, created_at) VALUES (?, ?, ?, ?, ?)",
        (uid, email, hash_password(password), (home_city or None), datetime.now(timezone.utc).isoformat()),
    )
    await conn.commit()
    return uid


async def authenticate(email: str, password: str) -> str | None:
    conn = await get_conn()
    cur = await conn.execute("SELECT id, pw_hash FROM users WHERE email = ?", (email.strip().lower(),))
    row = await cur.fetchone()
    if not row or not verify_password(password, row["pw_hash"]):
        return None
    return row["id"]


async def get_user(user_id: str) -> dict | None:
    conn = await get_conn()
    cur = await conn.execute("SELECT id, email, home_city FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def set_home_city(user_id: str, home_city: str | None) -> None:
    conn = await get_conn()
    await conn.execute("UPDATE users SET home_city = ? WHERE id = ?", (home_city or None, user_id))
    await conn.commit()
