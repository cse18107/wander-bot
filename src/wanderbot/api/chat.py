"""SSE chat endpoint.

Streams the agent's run as Server-Sent Events: token deltas plus tool start/end
steps, so the UI can show both the answer and the agent's reasoning trace.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from wanderbot.agents.react_agent import build_react_agent
from wanderbot.api.deps import get_principal, get_rate_limiter
from wanderbot.observability.logging import get_logger
from wanderbot.security import engine as guard_engine
from wanderbot.security import guardrails
from wanderbot.security.audit import audit
from wanderbot.security.auth import Principal
from wanderbot.security.ratelimit import RateLimiter

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])

# Built once per process; cheap to reuse across requests.
_agent = None


def _get_agent():  # noqa: ANN202 - CompiledStateGraph
    global _agent
    if _agent is None:
        _agent = build_react_agent()
    return _agent


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


async def _event_stream(req: ChatRequest, principal: Principal, safe_message: str) -> AsyncIterator[dict]:
    agent = _get_agent()
    config = {"configurable": {"thread_id": f"{principal.user_id}:{req.thread_id}"}}
    inputs = {"messages": [HumanMessage(content=safe_message)]}
    buffer: list[str] = []

    try:
        async for event in agent.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk.content:
                    buffer.append(chunk.content)
                    yield {"event": "token", "data": chunk.content}
            elif kind == "on_tool_start":
                yield {
                    "event": "tool_start",
                    "data": json.dumps(
                        {"tool": event["name"], "input": event["data"].get("input")}
                    ),
                }
            elif kind == "on_tool_end":
                yield {"event": "tool_end", "data": json.dumps({"tool": event["name"]})}
    except Exception as exc:  # pragma: no cover - surfaced to client
        log.error("chat_stream_error", error=str(exc))
        yield {"event": "error", "data": str(exc)}

    # Output rail on the assembled response (Bedrock or regex per config).
    final = await guard_engine.guard_output("".join(buffer), query=safe_message)
    if not final.allowed:
        yield {"event": "guard", "data": json.dumps({"blocked": True, "reasons": final.reasons})}
    elif final.reasons:
        yield {"event": "guard", "data": json.dumps({"redacted": True, "reasons": final.reasons})}
    yield {"event": "done", "data": "[DONE]"}


@router.post("/chat")
async def chat(
    req: ChatRequest,
    principal: Principal = Depends(get_principal),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> EventSourceResponse:
    if not await limiter.allow(f"chat:{principal.user_id}", limit=30, window_s=60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")

    # Input rail (Bedrock or regex per config): block jailbreaks/attacks, redact PII.
    rail = await guard_engine.guard_input(req.message)
    audit("chat_request", principal.user_id, decision=rail.decision.value, reasons=rail.reasons)
    if rail.decision is guardrails.Decision.BLOCK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "request blocked by input guardrail")

    return EventSourceResponse(_event_stream(req, principal, rail.text))
