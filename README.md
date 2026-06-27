# Wanderbot 🧭

Advanced multi-agent **holiday planning system** — LangGraph + LangChain + a first-party MCP server, wired to **real travel APIs** (Amadeus, Google Maps, OpenWeather, Tavily). Built as a senior-engineering reference: multi-agent orchestration, memory, layered security & guardrails, observability, testing, and a FastAPI + React UI.

> Design: [`DESIGN.md`](./DESIGN.md) · Roadmap: [`BUILD_PLAN.md`](./BUILD_PLAN.md)

## Status

All 13 phases built (see `BUILD_PLAN.md`): multi-agent graph, MCP server, memory,
RAG, security + **AWS Bedrock Guardrails**, observability, full test pyramid,
React UI, and Kubernetes/Helm deployment. ~50 deterministic tests green.

## Quickstart (local)

```bash
cp .env.example .env          # fill in OpenAI + Amadeus (free test) keys
uv pip install --system ".[dev]"
docker compose up -d postgres redis
uvicorn wanderbot.api.main:app --reload         # API on :8000

# UI (separate terminal)
cd ui && npm install && npm run dev             # http://localhost:5173

# tests
pytest -m "not live" -q                         # deterministic; live tests need creds
```

Key endpoints: `POST /api/plan` (multi-agent graph, SSE), `POST /api/plan/approve`
(HITL resume), `GET /api/preferences`, `/healthz`, `/metrics`.

## Deploy

```bash
helm upgrade --install wanderbot deploy/helm/wanderbot \
  -f deploy/helm/wanderbot/values-prod.yaml --namespace wanderbot
```
Separate API + MCP images, HPA + KEDA autoscaling, NetworkPolicy isolation, External
Secrets, atomic rollouts. CI/CD in `.github/workflows/`.

## Docs
- Architecture: [`DESIGN.md`](./DESIGN.md) · Roadmap: [`BUILD_PLAN.md`](./BUILD_PLAN.md)
- Decisions: [`docs/adr/`](./docs/adr) · Runbooks: [`docs/runbooks/`](./docs/runbooks)
- Demo script: [`docs/DEMO.md`](./docs/DEMO.md)

Run quality gates:

```bash
ruff check src tests
mypy src
pytest -m "not live" -q      # live sandbox tests need vendor creds
```

## Architecture (short)

```
React UI ──▶ FastAPI (auth · guardrails · SSE) ──▶ LangGraph orchestrator
                                                      │ supervisor + specialists
                          ┌───────────────────────────┼───────────────┐
                     MCP client                  memory (pg+pgvector)  RAG
                          │
                  Wanderbot MCP server ──▶ real APIs (Amadeus, Maps, Weather, FX)
```

## Layout

| Path | What |
|---|---|
| `src/wanderbot/config.py` | 12-factor settings |
| `src/wanderbot/llm_factory.py` | provider-pluggable LLM/embeddings |
| `src/wanderbot/api/` | FastAPI app, SSE chat |
| `src/wanderbot/providers/` | real API clients (Amadeus, ...) |
| `src/wanderbot/tools/` | LangChain tools |
| `src/wanderbot/agents/` | graph, supervisor, specialists |
| `mcp_server/` | standalone MCP server |
| `tests/` | unit · integration · agents · evals · redteam |

## License

MIT
