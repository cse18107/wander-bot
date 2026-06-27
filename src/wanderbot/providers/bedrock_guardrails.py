"""AWS Bedrock Guardrails client (ApplyGuardrail API).

Model-independent: assesses arbitrary text against a pre-configured guardrail
WITHOUT invoking a foundation model. The sync boto3 call is run in a thread so it
doesn't block the event loop. Response ``assessments`` are normalized into a small
set of categories the engine layer maps to rail decisions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Literal

from wanderbot.config import Settings, get_settings
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

Source = Literal["INPUT", "OUTPUT"]


@dataclass
class GuardrailVerdict:
    intervened: bool
    text: str  # possibly anonymized/masked output
    categories: list[str] = field(default_factory=list)  # PROMPT_ATTACK, PII, ...
    detail: dict[str, Any] = field(default_factory=dict)


class BedrockGuardrailsClient:
    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self._settings = settings or get_settings()
        self._client = client  # injectable for tests

    def _boto(self) -> Any:
        if self._client is None:
            import boto3  # imported lazily so the dep is optional

            self._client = boto3.client(
                "bedrock-runtime", region_name=self._settings.aws_region
            )
        return self._client

    async def apply(
        self,
        text: str,
        *,
        source: Source = "INPUT",
        grounding_source: str | None = None,
        query: str | None = None,
    ) -> GuardrailVerdict:
        gid = self._settings.bedrock_guardrail_id
        if not gid:
            raise RuntimeError("bedrock_guardrail_id not configured")

        content: list[dict[str, Any]] = []
        if grounding_source is not None:
            content.append(
                {"text": {"text": grounding_source, "qualifiers": ["grounding_source"]}}
            )
        if query is not None:
            content.append({"text": {"text": query, "qualifiers": ["query"]}})
        content.append({"text": {"text": text, "qualifiers": ["guard_content"]}})

        def _call() -> dict[str, Any]:
            return self._boto().apply_guardrail(
                guardrailIdentifier=gid,
                guardrailVersion=self._settings.bedrock_guardrail_version,
                source=source,
                content=content,
            )

        resp = await asyncio.to_thread(_call)
        return self._normalize(resp, fallback_text=text)

    @staticmethod
    def _normalize(resp: dict[str, Any], *, fallback_text: str) -> GuardrailVerdict:
        action = resp.get("action", "NONE")
        intervened = action == "GUARDRAIL_INTERVENED"

        # Masked/anonymized output, if any.
        text = fallback_text
        outputs = resp.get("outputs") or []
        if outputs and isinstance(outputs[0], dict):
            text = outputs[0].get("text", fallback_text)

        categories: list[str] = []
        for assessment in resp.get("assessments", []):
            content_pol = assessment.get("contentPolicy", {})
            for f in content_pol.get("filters", []):
                if f.get("action") in ("BLOCKED", "ANONYMIZED"):
                    categories.append(
                        "PROMPT_ATTACK" if f.get("type") == "PROMPT_ATTACK" else "CONTENT_FILTER"
                    )
            if assessment.get("topicPolicy", {}).get("topics"):
                categories.append("DENIED_TOPIC")
            sip = assessment.get("sensitiveInformationPolicy", {})
            if sip.get("piiEntities") or sip.get("regexes"):
                categories.append("PII")
            wp = assessment.get("wordPolicy", {})
            if wp.get("customWords") or wp.get("managedWordLists"):
                categories.append("WORD")
            cg = assessment.get("contextualGroundingPolicy", {})
            for f in cg.get("filters", []):
                if f.get("action") == "BLOCKED":
                    categories.append("GROUNDING")

        return GuardrailVerdict(
            intervened=intervened,
            text=text,
            categories=sorted(set(categories)),
            detail={"action": action},
        )
