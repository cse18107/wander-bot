# ADR-0003: Two-layer memory (checkpointer + long-term store)

**Status:** Accepted

## Context
Conversational continuity and cross-trip personalization are different problems and
are commonly conflated.

## Decision
- **Short-term:** a LangGraph checkpointer (`PostgresSaver`, in-memory fallback)
  keyed by `thread_id` — durable conversations, HITL pause/resume, time-travel.
- **Long-term:** a `LongTermMemory` store keyed by `user_id` (pgvector in prod,
  in-memory for dev/tests) — durable preferences, semantically recalled into new
  briefs. Namespaced per user; never crosses tenants.

## Consequences
- Pro: clean separation; each layer has the right durability and key.
- Pro: offline/dev needs no infra (fallbacks).
- Con: two storage paths to operate; acceptable and standard.
