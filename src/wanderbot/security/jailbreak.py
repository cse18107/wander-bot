"""Heuristic jailbreak / prompt-injection detection.

One layer of a layered defense (DESIGN.md §18). A fast heuristic scanner catches
common patterns; in production it sits in front of a model-based classifier
(Llama Guard / OpenAI moderation). Detectors are evadable individually — the
system's real protection is structural containment, not this scanner alone.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

_INJECTION_PATTERNS = [
    r"ignore\s+(?:\w+\s+){0,3}(instructions|prompts|rules|guidelines|guardrails)",
    r"disregard\s+(?:\w+\s+){0,3}(instructions|rules|context|guidelines|guardrails)",
    r"forget\s+(?:everything|all previous|your instructions)",
    r"you are now\s+(?:a|an|in)?\s*.{0,40}(dan|developer mode|jailbreak|unrestricted|unfiltered)",
    r"(reveal|show|print)\s+(?:\w+\s+){0,3}(system prompt|hidden prompt|instructions|api key|secret)",
    r"(act|behave)\s+as\s+(?:if\s+you\s+(?:have no|had no)\s+)?(?:an?\s+|the\s+)?"
    r"(restrictions|guidelines|rules|unrestricted|jailbroken|unfiltered|uncensored)",
    r"do anything now",
    r"override\s+(?:\w+\s+){0,2}(safety|security|guard|guardrail|rules|guidelines)",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]
_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


@dataclass
class RiskResult:
    blocked: bool
    score: float
    reasons: list[str] = field(default_factory=list)


def _decoded_text(text: str) -> str:
    """Surface base64-obfuscated payloads for scanning."""
    extra = []
    for token in _B64.findall(text):
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8", "ignore")
            if decoded.isprintable():
                extra.append(decoded)
        except Exception:
            continue
    return text + " " + " ".join(extra)


def scan(text: str, *, threshold: float = 0.5) -> RiskResult:
    haystack = _decoded_text(text)
    reasons = [p.pattern for p in _COMPILED if p.search(haystack)]
    score = min(1.0, 0.5 * len(reasons)) if reasons else 0.0
    return RiskResult(blocked=score >= threshold, score=score, reasons=reasons)
