# ADR-0006: Deterministic orchestration, LLM for judgment only

**Status:** Accepted

## Context
A supervisor can route via an LLM call per hop, or deterministically. LLM routing
adds latency, cost, and nondeterminism (hard to test) for a workflow whose happy
path and budget loop are a known sequence.

## Decision
Route **deterministically** (`agents/routing.py:decide_next`). Use the LLM only
where judgment is genuinely needed: intake parsing (`with_structured_output`),
itinerary authoring, and research synthesis. This makes the graph fully testable
with a seeded/fake model and keeps the budget<->replan loop bounded and predictable.

## Consequences
- Pro: deterministic graph tests, lower latency/cost, terminating loops.
- Pro: clear separation of "control flow" vs. "content decisions".
- Con: less "emergent" routing; acceptable — the domain flow is well-defined, and the
  swarm variant exists for those who want decentralized behavior.
