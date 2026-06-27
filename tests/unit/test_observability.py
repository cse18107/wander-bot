import pytest

from wanderbot.observability import metrics
from wanderbot.observability.cost import CostBudgetExceeded, CostTracker, estimate_cost


def test_cost_estimate_is_reasonable() -> None:
    cost = estimate_cost("gpt-4o-mini", prompt_tokens=1000, completion_tokens=1000)
    assert cost == pytest.approx(0.00015 + 0.0006, rel=1e-3)
    assert estimate_cost("unknown-model", 1000, 1000) == 0.0


class _Resp:
    def __init__(self, pt: int, ct: int):
        self.llm_output = {"token_usage": {"prompt_tokens": pt, "completion_tokens": ct}}


@pytest.mark.asyncio
async def test_cost_tracker_accumulates_and_enforces_budget() -> None:
    tracker = CostTracker("gpt-4o", budget_usd=0.01)
    await tracker.on_llm_end(_Resp(1000, 0))  # 0.0025
    assert tracker.cost_usd == pytest.approx(0.0025, rel=1e-3)

    with pytest.raises(CostBudgetExceeded):
        await tracker.on_llm_end(_Resp(10000, 0))  # pushes over 0.01


def test_guardrail_metric_increments() -> None:
    before = metrics.GUARDRAIL_DECISIONS.labels(rail="input", decision="allow")._value.get()
    metrics.guardrail_decision("input", "allow")
    after = metrics.GUARDRAIL_DECISIONS.labels(rail="input", decision="allow")._value.get()
    assert after == before + 1
