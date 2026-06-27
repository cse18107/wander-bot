# Wanderbot — Phase-Wise Build Plan

Companion to `DESIGN.md`. This is the execution roadmap: what to build, in what order, and how to know each phase is *done*. The ordering is deliberate — a runnable, real-API "walking skeleton" comes first, then the multi-agent depth, then production hardening. Every phase ends in something demoable.

**Effort estimates** assume one focused senior engineer; treat them as relative sizing, not commitments.

---

## Milestones at a glance

| Milestone | Phases | Outcome |
|---|---|---|
| **M0 — Walking skeleton** | 1–3 | One real agent answers a trip query using a live API behind the MCP server. "No mocks" proven end-to-end. |
| **M1 — Multi-agent brain** | 4–7 | Supervisor + specialists, budget replan loop, HITL, memory, and RAG. The system actually plans trips. |
| **M2 — Production hardening** | 8–10 | Security, guardrails, observability, and the full test pyramid. Safe to expose. |
| **M3 — Ship** | 11–13 | Polished UI, K8s deployment, docs. Demoable to interviewers / users. |

| Phase | Focus | Effort | Depends on |
|---|---|---|---|
| 1 | Foundations | S | — |
| 2 | Single real-API agent | M | 1 |
| 3 | MCP server | M | 2 |
| 4 | Multi-agent graph | L | 3 |
| 5 | Orchestration depth | L | 4 |
| 6 | Memory | M | 4 |
| 7 | RAG research | M | 4 |
| 8 | Security & guardrails | L | 5,6,7 |
| 9 | Observability | M | 5 |
| 10 | Testing | L | 5,6,7 |
| 11 | UI polish | M | 5 |
| 12 | Deployment & scale | L | 8,9,10 |
| 13 | Docs & demo | S | all |

---

# M0 — Walking skeleton

## Phase 1 · Foundations
**Goal:** a clean, runnable repo with config, quality gates, and one live HTTP route — before any agent code.

**Deliverables**
- `uv`-managed `pyproject.toml`, repo structure per `DESIGN.md` §5.
- `config.py` with `pydantic-settings` (12-factor), `.env.example`.
- `llm_factory` (provider-pluggable; OpenAI default).
- FastAPI app skeleton with `/healthz` and structured logging.
- `docker-compose.yml` (app + Postgres+pgvector + Redis), multi-stage `Dockerfile`.
- CI skeleton: `ruff`, `mypy --strict`, `pytest`, `pre-commit`.

**Exit criteria:** `docker compose up` runs; `/healthz` is green; CI passes on an empty test; `mypy` and `ruff` clean.
**Demo:** "It boots, it's typed, it's linted, CI is green."

## Phase 2 · Single real-API agent
**Goal:** one ReAct agent answers a trip-flavored question using a **real** external API — the first proof that "no mocks" holds.

**Deliverables**
- Amadeus OAuth2 **token manager** (cache + refresh) against the **test** environment.
- One real tool: `search_flights` (typed Pydantic args, validation, timeout/retry).
- A `create_react_agent` wired to OpenAI + that tool, with streaming.
- `/chat` SSE endpoint streaming tokens + tool events.
- Structured-output intake (`TripBrief`) so free text → typed fields.

**Exit criteria:** "cheapest flights NYC→Tokyo in October" returns real Amadeus offers, streamed to the client; bad input is rejected gracefully.
**Demo:** live flight results from a real API in a streaming chat.

## Phase 3 · MCP server
**Goal:** move travel tools behind a standalone MCP server consumed by the agent — the client/server boundary MCP is built for.

**Deliverables**
- `mcp_server/` standalone process (official `mcp` SDK), `stdio` transport first.
- `Provider` interface + Amadeus adapter (sandbox creds) for `search_flights`; stubs for `search_hotels`, `search_activities`.
- `MultiServerMCPClient` setup; `get_tools()` injects MCP tools into the agent at startup.
- Server-side input validation + per-tool rate limit.

**Exit criteria:** the Phase-2 flow works **identically** with the flight tool served over MCP; integration test does a real stdio round-trip against a vendor sandbox.
**Demo:** same result as Phase 2, now proving the tool runs in a separate, swappable MCP process.

---

# M1 — Multi-agent brain

## Phase 4 · Multi-agent graph
**Goal:** replace the single agent with a supervisor + specialist hierarchy on typed state.

**Deliverables**
- `TripState` (TypedDict + reducers) per `DESIGN.md` §6.2.
- **Supervisor** node + specialists: Research, Flights, Lodging, Activities, Itinerary (each a small subgraph).
- Real Amadeus adapters completed for hotels + activities.
- Conditional edges for routing; parallel fan-out for independent searches.
- `PostgresSaver` checkpointer wired (short-term memory) so runs are durable.

**Exit criteria:** a single brief produces a draft itinerary with real flights, hotels, and activities; routing is visible in traces; conversation survives a restart.
**Demo:** end-to-end draft trip plan from one natural-language request.

## Phase 5 · Orchestration depth
**Goal:** the control-flow showpieces — budget loop, replanning, human-in-the-loop.

**Deliverables**
- **Budget** specialist: sums selections vs target, emits `ok`/`over_budget`.
- **Replan loop:** over-budget → supervisor re-searches the most expensive component → re-check, bounded by a max-iteration guard.
- **HITL:** `interrupt()` before any "reserve" step; graph pauses and resumes from checkpoint on user decision.
- **Swarm variant** as an alternate entrypoint (direct `Command` handoffs) to demonstrate the tradeoff.

**Exit criteria:** an over-budget trip visibly replans down to target; the reserve step blocks until approved; both supervisor and swarm entrypoints work.
**Demo:** "make it $500 cheaper" triggers a real replan; approval gate stops the reserve.

## Phase 6 · Memory
**Goal:** the system learns user preferences across conversations.

**Deliverables**
- Long-term `BaseStore` on Postgres + pgvector, namespaced per `user_id`.
- Preference **extraction** step after a trip ("aisle seats, vegetarian, mid-range").
- Semantic retrieval of relevant memories injected into new briefs.
- Light procedural memory: store successful routing trajectories.

**Exit criteria:** a second trip for the same user auto-applies learned preferences; memory is per-user isolated.
**Demo:** "plan another trip" silently honors prior preferences.

## Phase 7 · RAG research
**Goal:** grounded destination/seasonality research with citations.

**Deliverables**
- Ingestion pipeline for a curated destination KB into pgvector.
- Hybrid retriever (vector + BM25) with a rerank step.
- Research specialist uses RAG **plus** the live web-search tool (Tavily); claims carry citations.

**Exit criteria:** research answers cite sources; "best time to visit" reflects real seasonality/weather data; ungrounded claims are flagged.
**Demo:** a research answer with traceable citations feeding the plan.

---

# M2 — Production hardening

## Phase 8 · Security & guardrails
**Goal:** make it safe to expose — the four-rail guardrail system and the full security posture.

**Deliverables**
- JWT auth at the gateway; authz at route, tool, and memory layers.
- The four guardrail checkpoints (`DESIGN.md` §18): input, content (untrusted tool/RAG output), tool-arg (approval-token gating), output rails.
- Jailbreak detection (NeMo Guardrails + OpenAI moderation + heuristics).
- PII detection/redaction (Presidio); secrets via secrets manager; per-user/IP rate limits; per-request token/cost budgets; audit log.
- `docs/threat-model.md`, `docs/provider-terms.md`.

**Exit criteria:** red-team payloads (injection via "reviews", approval-skip attempts, PII exfil) are blocked; rate/cost limits trip correctly; every rail decision emits a span.
**Demo:** a malicious "hotel review" tries to hijack the planner and is caught and traced.

## Phase 9 · Observability
**Goal:** full traceability of every run, token, and dollar.

**Deliverables**
- LangSmith tracing + OpenTelemetry export; OTel Collector in compose.
- Prometheus metrics + Grafana dashboards (latency, tokens, cost, tool error rate, budget-loop iterations, retrieval hit rate, guardrail block rate).
- Cost-tracking callback (LLM **and** external-API spend) per request/user/agent.
- Live evals on a sampled slice of traffic.

**Exit criteria:** a single trip is fully reconstructable in a trace with `user_id`/`thread_id`/`agent`/`tool` attributes and a cost figure; dashboards populate.
**Demo:** open one trace and walk every LLM call, tool call, guardrail decision, and its cost.

## Phase 10 · Testing
**Goal:** fill the pyramid and gate releases.

**Deliverables**
- Unit (budget math, geo, parsers, reducers), integration (routes, MCP round-trip via `vcrpy` cassettes, checkpointer, memory).
- Deterministic **graph tests** with a seeded/fake LLM: routing, replan loop, HITL interrupt/resume.
- Evals (rule-based + LLM-judge) on a LangSmith dataset: geographic coherence, budget adherence, preference honoring, citations.
- Red-team suite + nightly live-sandbox contract test.
- CI gates: coverage threshold, eval pass rate, red-team pass rate, `mypy`/`ruff`.

**Exit criteria:** all gates enforced in CI; a deliberately broken router/replan fails a test.
**Demo:** CI run showing unit→integration→eval→red-team all green as a merge gate.

---

# M3 — Ship

## Phase 11 · UI polish
**Goal:** the medium-complexity, real-time interface.

**Deliverables**
- React + Vite + TS + Tailwind: streaming chat with collapsible agent steps.
- Live **itinerary panel** (flights, hotel, day cards, running budget bar).
- **Approval modal** wired to the HITL interrupt.
- Preferences view with a "forget" affordance (privacy).

**Exit criteria:** a non-technical user can plan and approve a trip in the browser; itinerary updates live; approval gate surfaces in the UI.
**Demo:** full browser walkthrough from prompt to approved itinerary.

## Phase 12 · Deployment & scale
**Goal:** stateless horizontal scale on Kubernetes.

**Deliverables**
- Multi-stage, non-root images for app + MCP server; Trivy scan + SBOM in CI.
- Helm chart (dev/staging/prod overlays): Deployments with resource limits + probes, **HPA** (API tier) + **KEDA** (worker tier on queue depth), PodDisruptionBudget.
- Managed/operator Postgres+pgvector and Redis; External Secrets for API keys; `NetworkPolicy` isolating the MCP server; TLS Ingress.
- CD: build→scan→push→Helm deploy to staging→smoke/eval/red-team gates→manual promote to prod with auto-rollback.

**Exit criteria:** rolling deploy with zero dropped in-flight conversations (checkpoint-backed); HPA/KEDA scale under a load test; secrets never in image/manifests.
**Demo:** load test scales pods out and back; a mid-conversation pod restart resumes cleanly.

## Phase 13 · Docs & demo
**Goal:** make it legible to a reviewer.

**Deliverables**
- README with architecture diagram + quickstart; ADRs (supervisor-vs-swarm, MCP-as-process, memory layering, Amadeus anchor).
- Runbooks (incident, rollback) and the interview talking-points (`DESIGN.md` §16).
- A scripted end-to-end demo + short recording.

**Exit criteria:** a new engineer clones, runs `docker compose up`, and traces a trip end-to-end from the README alone.
**Demo:** the 5-minute guided walkthrough.

---

## Build principles (apply every phase)

- **Vertical slices, not horizontal layers** — each phase delivers a thin end-to-end capability you can demo, never a half-finished tier.
- **Real APIs from Phase 2** — no mock providers ever enter the codebase; sandboxes stand in for prod credentials, same code path.
- **Tests land with the feature**, not in a later "testing phase" — Phase 10 *completes* the pyramid and gates; it doesn't start it.
- **Keep `main` releasable** — every merge is green, typed, and deployable.

---

## Suggested starting point

Begin **Phase 1 → Phase 2**: foundations, then the Amadeus token manager + one real `search_flights` tool in a streaming agent. That single slice proves the highest-risk assumptions (real-API auth, streaming, typed intake) before any multi-agent complexity is added.
