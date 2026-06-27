"""PII detection & redaction.

Regex-based by default (zero-dependency, deterministic). In production this can be
swapped for Microsoft Presidio behind the same ``detect``/``redact`` interface.
Applied to inbound text and before anything is written to memory or logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[ -]?)?(?:\(?\d{3}\)?[ -]?)\d{3}[ -]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "passport": re.compile(r"\b[A-Z]{1,2}\d{7}\b"),
}


@dataclass
class PIIMatch:
    kind: str
    value: str


def detect(text: str) -> list[PIIMatch]:
    found: list[PIIMatch] = []
    for kind, pattern in _PATTERNS.items():
        for m in pattern.findall(text):
            value = m if isinstance(m, str) else "".join(m)
            found.append(PIIMatch(kind=kind, value=value))
    return found


def redact(text: str) -> str:
    out = text
    for kind, pattern in _PATTERNS.items():
        out = pattern.sub(f"[REDACTED_{kind.upper()}]", out)
    return out


def has_pii(text: str) -> bool:
    return bool(detect(text))
