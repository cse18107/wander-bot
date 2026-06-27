"""Structured, append-only audit log.

Every tool call, approval, guardrail block, and memory write is recorded with the
acting user (hashed) so actions are reconstructable. PII is redacted before write.
"""

from __future__ import annotations

import hashlib

from wanderbot.observability.logging import get_logger
from wanderbot.security.pii import redact

_audit_log = get_logger("audit")


def _hash_user(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


def audit(action: str, user_id: str, **fields: object) -> None:
    safe = {k: (redact(v) if isinstance(v, str) else v) for k, v in fields.items()}
    _audit_log.info("audit", action=action, user=_hash_user(user_id), **safe)
