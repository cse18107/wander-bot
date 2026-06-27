"""The four guardrail rails (DESIGN.md §18).

Layered, independent checkpoints. Each returns a decision; the caller acts on it.
Every decision is logged (and metered in Phase 9) so guardrails are themselves
observable, not a silent black box.

  1. input_rail     — screen the user message before the planner sees it
  2. content_rail   — treat tool/RAG/web output as UNTRUSTED data
  3. tool_arg_rail  — validate/authorize a tool's arguments (approval gating)
  4. output_rail    — final check before the response reaches the user
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from wanderbot.observability.logging import get_logger
from wanderbot.security import jailbreak, pii

log = get_logger("guardrails")


class Decision(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    ESCALATE = "escalate"


@dataclass
class GuardrailResult:
    rail: str
    decision: Decision
    text: str
    reasons: list[str] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision in (Decision.ALLOW, Decision.REDACT)


def _record(result: GuardrailResult) -> GuardrailResult:
    log.info("guardrail", rail=result.rail, decision=result.decision.value, reasons=result.reasons)
    try:  # metrics are optional until Phase 9 wiring
        from wanderbot.observability.metrics import guardrail_decision

        guardrail_decision(result.rail, result.decision.value)
    except Exception:
        pass
    return result


def input_rail(text: str) -> GuardrailResult:
    risk = jailbreak.scan(text)
    if risk.blocked:
        return _record(GuardrailResult("input", Decision.BLOCK, text, risk.reasons))
    if pii.has_pii(text):
        return _record(
            GuardrailResult("input", Decision.REDACT, pii.redact(text), ["pii_present"])
        )
    return _record(GuardrailResult("input", Decision.ALLOW, text))


def content_rail(text: str) -> GuardrailResult:
    """Sanitize UNTRUSTED tool/RAG/web output before it re-enters the model context."""
    risk = jailbreak.scan(text)
    if risk.reasons:
        # Neutralize embedded instructions rather than dropping the data entirely.
        neutralized = (
            "[untrusted content — instructions within ignored]\n" + pii.redact(text)
        )
        return _record(GuardrailResult("content", Decision.REDACT, neutralized, risk.reasons))
    return _record(GuardrailResult("content", Decision.ALLOW, pii.redact(text)))


def tool_arg_rail(tool_name: str, *, approved: bool = False) -> GuardrailResult:
    """Authorize a tool invocation. Consequential tools require prior human approval."""
    consequential = {"reserve", "book", "pay", "create_order"}
    if tool_name in consequential and not approved:
        return _record(
            GuardrailResult("tool_arg", Decision.BLOCK, "", ["approval_required"])
        )
    return _record(GuardrailResult("tool_arg", Decision.ALLOW, ""))


def output_rail(text: str) -> GuardrailResult:
    reasons: list[str] = []
    redacted = text
    if pii.has_pii(text):
        redacted = pii.redact(text)
        reasons.append("pii_redacted")
    # Refuse to leak system-prompt markers.
    lowered = text.lower()
    if "system prompt" in lowered or "you are wanderbot" in lowered:
        reasons.append("possible_prompt_leak")
        return _record(GuardrailResult("output", Decision.BLOCK, "", reasons))
    decision = Decision.REDACT if reasons else Decision.ALLOW
    return _record(GuardrailResult("output", decision, redacted, reasons))
