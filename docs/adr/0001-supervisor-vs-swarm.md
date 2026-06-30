# ADR-0001: Supervisor as default orchestration (swarm as alternative)

**Status:** Accepted

## Context
Multi-agent coordination can be centralized (a supervisor routes every step) or
decentralized (specialists hand off directly — a "swarm"). We need accuracy,
auditability, and a bounded budget-optimization loop, while still demonstrating
awareness of the latency tradeoff.

## Decision
Use a **supervisor** as the default (`agents/graph.py`): one accountable node owns
routing; every action passes through it, making traces and authorization checks
easy. Ship a **swarm variant** (`agents/swarm.py`) as an alternate entrypoint using
`Command(goto=...)` handoffs.

Routing in the supervisor is **deterministic** (a state machine), not an LLM call
per hop — see ADR-0006.

## Consequences
- Pro: predictable control flow, single audit point, trivial to test, easy HITL gate.
- Pro: swarm available when latency matters (one fewer hop per step).
- Con: the supervisor is an extra hop vs. direct handoff; accepted for accuracy and
  observability.
