# Roam (Wanderbot) — Project Context & Handoff

A complete brief so a new engineer (or a new Claude session) can pick this project
up cold. Read this first, then `DESIGN.md`, then `deploy/lightsail/OPERATIONS.md`.

---

## 1. What this is

**Roam** is an advanced, multi-agent **holiday-planning assistant**. A user
describes a trip ("7 days in London, mid-range budget, flying from Kolkata") and
the system builds a full itinerary: real flights/ground transport, hotels,
day-by-day plans, budget in the user's home currency, photos, and a conversational
"Trip Assistant" chat to refine everything.

> The internal/package name is **`wanderbot`**; the user-facing brand is **Roam**.
> Both refer to the same project. The repo is historically named `wander-bot`.

---

## 2. Current status (TL;DR)

- **Fully built and deployed in production.** Live at **https://roamtrips.duckdns.org**.
- Runs on a single **AWS Lightsail** 2 GB instance (Mumbai / `ap-south-1`), ~**$12/month**.
- **Push-to-deploy CI/CD** via GitHub Actions: push to `main` → auto-deploys.
- **AWS Bedrock Guardrails** enforce on both chat surfaces (input + output):
  jailbreak/prompt-injection blocked, PII (cards/SSN/etc.) blocked, contact info
  masked, profanity filtered — verified working.
- Originally targeted **EKS** (Terraform + Helm exist in the repo) but that was
  **abandoned for cost** (~₹25k/mo) in favor of Lightsail (~₹1k/mo). The EKS IaC is
  left in the repo for reference but is **not used**.

---

## 3. Live deployment — where & how it runs

| Thing | Value |
|---|---|
| Host | AWS Lightsail instance `wanderbot`, region `ap-south-1`, plan `small_3_1` (2 GB) |
| Public IP | `13.206.150.1` (static, named `wanderbot-ip`) |
| Domain | `https://roamtrips.duckdns.org` (DuckDNS free subdomain → A record to the IP) |
| TLS | Automatic via **Caddy** + Let's Encrypt |
| SSH | `ssh -i ~/wanderbot-lightsail.pem ubuntu@13.206.150.1` |
| App folder on box | `~/wanderbot` (synced from the repo) |
| Runtime | `docker compose` — see `deploy/lightsail/docker-compose.prod.yml` |
| Secrets on box | `~/wanderbot/deploy/lightsail/.env` (NOT in Git) |

**Container topology** (single box, all via compose):

```
Internet → Caddy (:80/:443, TLS) → web (Nginx, serves SPA, proxies /api)
                                       → app (FastAPI :8000, runs the MCP server as a subprocess)
                                            → postgres (pgvector)
                                            → redis
```

The API container also launches the MCP server in-process (`mcp_server_cmd`), so
there is **no separate MCP container** in this deployment (the Helm/EKS setup had
one; compose does not).

Full operational commands (start/stop, logs, env edits, teardown) are in
**`deploy/lightsail/OPERATIONS.md`** — that's the day-to-day runbook.

---

## 4. Tech stack

- **Agents**: LangGraph (supervisor graph, deterministic routing, HITL via
  `interrupt_before`), LangChain, first-party **MCP server**.
- **LLM**: provider-pluggable via `src/wanderbot/llm_factory.py`. Currently
  **Gemini `gemini-2.5-flash`** (also supports OpenAI). Embeddings via the same provider.
- **API**: FastAPI + SSE streaming (`src/wanderbot/api/`).
- **UI**: React + Vite + TypeScript (`ui/`), Plus Jakarta Sans font, Material Symbols.
- **Data**: SQLAlchemy async. **Postgres (pgvector)** in prod; SQLite for local dev.
- **Real APIs**: Duffel (flights + stays), Tavily (web search + images),
  Open-Meteo (weather), Frankfurter (FX). Amadeus client exists but is legacy/optional.
- **Security**: layered guardrails (regex + **AWS Bedrock Guardrails**), JWT auth,
  PII redaction, jailbreak detection, rate limiting.
- **Infra**: Docker, docker-compose, Caddy, Nginx. (Unused: Terraform + Helm for EKS.)

---

## 5. Architecture (short)

```
React UI ──▶ FastAPI (auth · guardrails · SSE) ──▶ LangGraph orchestrator
                                                      │ supervisor + specialists
                          ┌───────────────────────────┼───────────────┐
                     MCP client                  memory (pg+pgvector)  RAG
                          │
                  Wanderbot MCP server ──▶ real APIs (Duffel, Tavily, Weather, FX)
```

- **Graph**: `src/wanderbot/agents/graph.py`, routing in `routing.py`, nodes in
  `nodes.py`, shared state in `state.py`, schemas in `schemas.py`.
- **Multi-leg trips**: a trip can have multiple stops; each "leg" gets its own
  transport choice (interactive HITL pick per hop) and its own stacked itinerary.
- **HITL gates**: flight/transport selection and final approval pause the graph
  (`interrupt_before`) and resume via API endpoints.
- **Two chat surfaces**, both guarded (input + output):
  1. The **planning flow** (`/api/plan`, plus the in-plan "Trip Assistant" with
     tools: attach images, show options, modify plan, set budget tier) — in `api/plan.py`.
  2. The **streaming chat** endpoint — in `api/chat.py`.

See `DESIGN.md` and `docs/adr/` for deeper rationale.

---

## 6. Repository layout

| Path | What |
|---|---|
| `src/wanderbot/config.py` | 12-factor settings (env prefix `WB_`) |
| `src/wanderbot/llm_factory.py` | provider-pluggable LLM/embeddings |
| `src/wanderbot/api/` | FastAPI app, SSE, plan + chat endpoints |
| `src/wanderbot/agents/` | LangGraph graph, supervisor, specialist nodes, state |
| `src/wanderbot/providers/` | real API clients (Duffel, Tavily, weather, FX, Bedrock) |
| `src/wanderbot/security/` | guardrails engine, auth, PII, jailbreak, rate limit |
| `src/wanderbot/storage/` | app store (users, plans, chat threads) via SQLAlchemy |
| `src/wanderbot/memory/` | checkpointer, pgvector store, preferences |
| `mcp_server/` | standalone MCP server (run as a subprocess of the API) |
| `ui/` | React + Vite frontend (Dockerfile builds + serves via Nginx) |
| `deploy/lightsail/` | **the live deployment**: compose, Caddyfile, .env.example, OPERATIONS.md |
| `deploy/bedrock/` | `create-guardrail.sh` — creates the Bedrock guardrail |
| `deploy/helm/` | Helm chart for EKS — **unused** (kept for reference) |
| `infra/terraform/` | Terraform for EKS — **unused / destroyed** (kept for reference) |
| `.github/workflows/` | `ci.yml` (advisory), `deploy.yml` (CD to Lightsail) |
| `tests/` | unit · integration · agents · evals · redteam |

---

## 7. Local development

```bash
cp .env.example .env          # fill in keys (OpenAI/Gemini + Duffel + Tavily)
uv pip install --system ".[dev]"
docker compose up -d postgres redis
uvicorn wanderbot.api.main:app --reload         # API on :8000

cd ui && npm install && npm run dev             # http://localhost:5173

pytest -m "not live" -q                         # deterministic tests
```

Local app store defaults to **SQLite** (zero-config). Set `WB_APP_STORE_URL` to a
Postgres URL to use Postgres locally.

---

## 8. Configuration & secrets

All settings are env vars with prefix **`WB_`** (parsed by `config.py`). In
production they live **only** in `~/wanderbot/deploy/lightsail/.env` on the server
(git-ignored). Template: `deploy/lightsail/.env.example`.

Important keys:

```
POSTGRES_PASSWORD            # Postgres + app DB URL
WB_JWT_SECRET                # signs login tokens
WB_LLM_PROVIDER=gemini       # or openai
WB_LLM_MODEL=gemini-2.5-flash
WB_GOOGLE_API_KEY            # (or WB_OPENAI_API_KEY)
WB_DUFFEL_API_KEY            # flights
WB_TAVILY_API_KEY            # search + images
WB_GUARDRAILS_BACKEND=bedrock
WB_BEDROCK_GUARDRAIL_ID      # the guardrail to enforce
WB_AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY   # IAM creds boto3 uses for Bedrock
```

> **Security**: never commit `.env`. Editing env requires recreating the app
> container (`docker compose ... up -d --force-recreate app`). Any key pasted in
> chat during setup should be rotated.

---

## 9. Deployment & CI/CD

**Auto-deploy:** push to `main` → GitHub Actions **CD** (`deploy.yml`) SSHes into
the box, rsyncs the source, and runs `docker compose up -d --build`. Build happens
**on the box** (no image registry), ~3–5 min.

**GitHub repo secrets** (Settings → Secrets and variables → Actions):
- `LIGHTSAIL_SSH_KEY` — contents of the `.pem`
- `LIGHTSAIL_HOST` — `13.206.150.1`

**CI** (`ci.yml`): frontend build + ruff/mypy/pytest. The Python `quality` checks
are currently **advisory** (`continue-on-error: true`) because the codebase has
~136 pre-existing lint findings that never ran before — see "Known issues".

Manual deploy on the box: `cd ~/wanderbot/deploy/lightsail && docker compose -f docker-compose.prod.yml up -d --build`.

---

## 10. AWS Bedrock Guardrails

- Created via `deploy/bedrock/create-guardrail.sh` (covers content filters incl.
  **PROMPT_ATTACK** for jailbreak, PII block/anonymize tuned for travel, profanity).
- Applied in `src/wanderbot/security/engine.py` via
  `src/wanderbot/providers/bedrock_guardrails.py` (`ApplyGuardrail` API).
- Enforced on **both** chats, input and output (call sites in `api/plan.py` and
  `api/chat.py`: `guard_input`, `guard_output`, `guard_content`).
- **PII tuning note**: `ADDRESS` and `NAME` are intentionally **not** masked —
  otherwise hotel addresses and landmark names (legitimate travel content) would be
  redacted. Cards/CVV/SSN/passwords are hard-blocked; email/phone are anonymized.
- Verified: greetings pass, jailbreak blocked, card numbers blocked.

---

## 11. Key decisions & history

- **EKS → Lightsail**: EKS (Terraform + Helm) was fully built, then abandoned —
  the always-on cost (~₹25k/mo: control plane + NAT + RDS + ElastiCache + LB) was
  ~25× the user's ~₹1k/mo budget. All EKS infra was `terraform destroy`-ed. The
  single-box Lightsail + docker-compose path replaced it.
- **Build on the box** (no registry) to keep things simple for a solo dev.
- **CD decoupled from CI** so deploys aren't blocked by the never-green lint suite.
- **DuckDNS + Caddy** for a free domain + free auto-HTTPS (user is not a student,
  so GitHub Student Pack domains weren't an option).
- **Gemini `gemini-2.5-flash`** as the LLM (the old `gemini-1.5-flash` default 404s).

---

## 12. Bugs fixed during deployment (gotchas to know)

- **Postgres schema never created**: the legacy `ALTER TABLE` ran in the *same*
  transaction as the `CREATE TABLE`s; on Postgres a failed statement aborts the
  whole transaction and rolled the tables back. Fixed in `storage/db.py` — the
  ALTER now runs in its own transaction and is SQLite-only.
- **Bedrock "input is in incorrect format"**: `ApplyGuardrail` only accepts
  `qualifiers` for contextual-grounding checks. Plain moderation must send minimal
  `{"text": {"text": ...}}`. Fixed in `providers/bedrock_guardrails.py`.
- **Gemini 404**: default model bumped to `gemini-2.5-flash` (and set via `WB_LLM_MODEL`).
- **CI install**: GitHub runner's system Python is externally-managed + non-writable;
  switched to `uv venv` + `uv run`.

---

## 13. Known issues / deferred work

- **Lint cleanup (deferred)**: ~136 ruff findings (mostly `E501` long prompt
  strings + auto-fixable mechanical issues). `B008`/`S110`/`S112`/`RUF001-003` are
  ignored in `pyproject.toml` as intentional. CI `quality` is advisory until a real
  cleanup; then remove `continue-on-error` in `ci.yml`.
- **mypy / pytest on the runner**: never verified green (advisory). May surface issues.
- **Optional hardening**: denied-topics in the guardrail (e.g. block medical/legal
  advice to stay on-domain) not added.
- **Cost**: stopping the Lightsail instance does NOT reduce billing (flat rate);
  only deletion does. DB lives on the instance disk — back it up before teardown.

---

## 14. Operations

Day-to-day commands (connect, start/stop, logs, env management, GitHub Actions,
full teardown) are documented in **`deploy/lightsail/OPERATIONS.md`**. Start there
for anything operational.

---

## 15. Suggested next steps (backlog)

1. Real lint/type cleanup → flip CI back to a hard gate.
2. Add denied-topics to the guardrail for stricter on-domain behavior.
3. Automated DB backups (e.g. `pg_dump` to a cheap S3 bucket on a cron).
4. Consider serving the SPA's static assets via Caddy directly (drop the Nginx
   container) to shave memory on the 2 GB box.
5. Add a `/healthz`-based uptime check / alert.
```
