"""Token & cost accounting.

A LangChain callback tallies prompt/completion tokens and dollar cost per run, and
a per-request budget guard aborts runaway loops (DESIGN.md §10/§11). Prices are a
small editable table; external-API spend is tracked separately in providers.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler

from wanderbot.observability import metrics
from wanderbot.observability.logging import get_logger

log = get_logger(__name__)

# USD per 1K tokens (prompt, completion). Editable; keep roughly current.
_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p, c = _PRICES.get(model, (0.0, 0.0))
    return round((prompt_tokens / 1000) * p + (completion_tokens / 1000) * c, 6)


class CostBudgetExceeded(RuntimeError):
    pass


class CostTracker(AsyncCallbackHandler):
    def __init__(self, model: str, budget_usd: float | None = None):
        self.model = model
        self.budget_usd = budget_usd
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0

    async def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        usage = {}
        try:
            usage = (response.llm_output or {}).get("token_usage", {})
        except Exception:
            usage = {}
        pt = int(usage.get("prompt_tokens", 0))
        ct = int(usage.get("completion_tokens", 0))
        self.prompt_tokens += pt
        self.completion_tokens += ct
        cost = estimate_cost(self.model, pt, ct)
        self.cost_usd += cost

        metrics.record_tokens(self.model, pt, ct)
        metrics.record_cost(self.model, cost)

        if self.budget_usd is not None and self.cost_usd > self.budget_usd:
            log.warning("cost_budget_exceeded", cost=self.cost_usd, budget=self.budget_usd)
            raise CostBudgetExceeded(f"request cost ${self.cost_usd:.4f} exceeded ${self.budget_usd}")
