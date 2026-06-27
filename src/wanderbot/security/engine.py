"""Pluggable guardrail engines.

The four rails delegate to an *engine*. Two engines exist behind one async
interface:

- ``RegexEngine`` — the offline heuristic layer (zero infra/credentials).
- ``BedrockEngine`` — AWS Bedrock Guardrails (``ApplyGuardrail``), the authoritative
  managed detector. It runs the regex pre-filter first (cheap, blocks the obvious
  for free) and only spends a Bedrock call on what passes; any AWS error falls back
  to regex so the system fails safe and offline tests stay green.

Selection is config-driven (``WB_GUARDRAILS_BACKEND`` = auto | regex | bedrock).
"""

from __future__ import annotations

from typing import Protocol

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger
from wanderbot.security import guardrails as rg
from wanderbot.security.guardrails import Decision, GuardrailResult

log = get_logger(__name__)

# Bedrock categories that should hard-block.
_BLOCK_CATEGORIES = {"PROMPT_ATTACK", "CONTENT_FILTER", "DENIED_TOPIC", "WORD", "GROUNDING"}


class GuardrailEngine(Protocol):
    async def check_input(self, text: str) -> GuardrailResult: ...
    async def check_content(self, text: str) -> GuardrailResult: ...
    async def check_output(
        self, text: str, *, grounding_source: str | None = None, query: str | None = None
    ) -> GuardrailResult: ...


class RegexEngine:
    """Wraps the synchronous regex rails in the async engine interface."""

    async def check_input(self, text: str) -> GuardrailResult:
        return rg.input_rail(text)

    async def check_content(self, text: str) -> GuardrailResult:
        return rg.content_rail(text)

    async def check_output(
        self, text: str, *, grounding_source: str | None = None, query: str | None = None
    ) -> GuardrailResult:
        return rg.output_rail(text)


class BedrockEngine:
    """Bedrock Guardrails with a regex pre-filter and regex fallback."""

    # Substrings that mark a permanent (not transient) Bedrock failure — once
    # seen, stop calling Bedrock and serve the regex engine for the rest of the
    # process instead of retrying and log-spamming on every request.
    _PERMANENT_ERRORS = (
        "unable to locate credentials",
        "no credentials",
        "invalid security token",
        "the security token included in the request is invalid",
        "could not connect to the endpoint",
        "accessdenied",
    )

    def __init__(self, client=None, settings: Settings | None = None):
        self._settings = settings or get_settings()
        if client is None:
            from wanderbot.providers.bedrock_guardrails import BedrockGuardrailsClient

            client = BedrockGuardrailsClient(self._settings)
        self._client = client
        self._degraded = False  # set True after a permanent failure -> regex only

    @staticmethod
    def _to_result(rail: str, verdict, fallback_text: str) -> GuardrailResult:
        if not verdict.intervened:
            return GuardrailResult(rail, Decision.ALLOW, verdict.text, ["bedrock:clean"])
        block = [c for c in verdict.categories if c in _BLOCK_CATEGORIES]
        if block:
            return GuardrailResult(rail, Decision.BLOCK, "", [f"bedrock:{c}" for c in block])
        # PII-only intervention -> use the anonymized text.
        return GuardrailResult(rail, Decision.REDACT, verdict.text, ["bedrock:PII"])

    async def _guard(self, rail: str, text: str, *, source, **kw) -> GuardrailResult:
        # Cheap pre-filter first; if it already blocks, skip the Bedrock spend.
        pre = (
            rg.input_rail(text)
            if source == "INPUT"
            else rg.output_rail(text)
        )
        if pre.decision is Decision.BLOCK:
            log.info("guardrail_prefilter_block", rail=rail)
            return pre
        # Bedrock was already found unreachable (e.g. no AWS creds) -> regex only.
        if self._degraded:
            return pre
        try:
            verdict = await self._client.apply(text, source=source, **kw)
            return self._to_result(rail, verdict, text)
        except Exception as exc:  # fail safe to regex
            msg = str(exc)
            if any(p in msg.lower() for p in self._PERMANENT_ERRORS):
                # Permanent: disable Bedrock for the rest of the process, log once.
                self._degraded = True
                log.warning(
                    "bedrock_guardrail_disabled",
                    rail=rail,
                    error=msg,
                    note="Bedrock unreachable; using regex guardrails. Configure AWS "
                    "credentials or set WB_GUARDRAILS_BACKEND=regex to silence this.",
                )
            else:
                # Transient: fall back this once, may recover next request.
                log.warning("bedrock_guardrail_fallback", rail=rail, error=msg)
            return pre

    async def check_input(self, text: str) -> GuardrailResult:
        return await self._guard("input", text, source="INPUT")

    async def check_content(self, text: str) -> GuardrailResult:
        # Untrusted third-party content evaluated as INPUT (catches embedded attacks).
        result = await self._guard("content", text, source="INPUT")
        if result.decision is Decision.ALLOW:
            # Still strip PII from data we feed back into the model.
            from wanderbot.security import pii

            return GuardrailResult("content", Decision.ALLOW, pii.redact(result.text), result.reasons)
        if result.decision is Decision.BLOCK:
            # Neutralize rather than drop, mirroring the regex content rail.
            return GuardrailResult(
                "content",
                Decision.REDACT,
                "[untrusted content — flagged by Bedrock, instructions ignored]",
                result.reasons,
            )
        return result

    async def check_output(
        self, text: str, *, grounding_source: str | None = None, query: str | None = None
    ) -> GuardrailResult:
        return await self._guard(
            "output", text, source="OUTPUT", grounding_source=grounding_source, query=query
        )


_engine: GuardrailEngine | None = None


def get_engine(settings: Settings | None = None) -> GuardrailEngine:
    global _engine
    if _engine is not None:
        return _engine
    settings = settings or get_settings()
    if settings.bedrock_guardrails_enabled:
        log.info("guardrail_engine", backend="bedrock")
        _engine = BedrockEngine(settings=settings)
    else:
        log.info("guardrail_engine", backend="regex")
        _engine = RegexEngine()
    return _engine


def reset_engine() -> None:
    """Test hook to clear the cached engine."""
    global _engine
    _engine = None


# --- async rail entrypoints used by the app ---------------------------------
async def guard_input(text: str) -> GuardrailResult:
    return await get_engine().check_input(text)


async def guard_content(text: str) -> GuardrailResult:
    return await get_engine().check_content(text)


async def guard_output(
    text: str, *, grounding_source: str | None = None, query: str | None = None
) -> GuardrailResult:
    return await get_engine().check_output(text, grounding_source=grounding_source, query=query)
