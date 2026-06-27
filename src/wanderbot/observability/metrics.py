"""Prometheus metrics.

Exposed at ``/metrics``. Counters/histograms for latency, tokens, cost, tool
errors, guardrail decisions, and budget-loop iterations so the system's behavior
is dashboardable (DESIGN.md §11).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

REQUEST_LATENCY = Histogram(
    "wb_request_latency_seconds",
    "End-to-end request latency",
    ["endpoint"],
)

LLM_TOKENS = Counter(
    "wb_llm_tokens_total",
    "LLM tokens consumed",
    ["model", "kind"],  # kind = prompt | completion
)

LLM_COST_USD = Counter(
    "wb_llm_cost_usd_total",
    "Estimated LLM cost in USD",
    ["model"],
)

TOOL_ERRORS = Counter(
    "wb_tool_errors_total",
    "Tool invocation errors",
    ["tool"],
)

GUARDRAIL_DECISIONS = Counter(
    "wb_guardrail_decisions_total",
    "Guardrail rail decisions",
    ["rail", "decision"],
)

BUDGET_ITERATIONS = Counter(
    "wb_budget_loop_iterations_total",
    "Budget replan iterations executed",
)


def guardrail_decision(rail: str, decision: str) -> None:
    GUARDRAIL_DECISIONS.labels(rail=rail, decision=decision).inc()


def record_tokens(model: str, prompt: int, completion: int) -> None:
    LLM_TOKENS.labels(model=model, kind="prompt").inc(prompt)
    LLM_TOKENS.labels(model=model, kind="completion").inc(completion)


def record_cost(model: str, usd: float) -> None:
    LLM_COST_USD.labels(model=model).inc(usd)
