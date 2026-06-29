# Deployment runbook

Wanderbot ships as **three images** built from this repo:

| Image | Source | Serves |
|-------|--------|--------|
| `wanderbot-api` | `Dockerfile` | FastAPI backend (`/api`, `/healthz`, `/metrics`) on :8000 |
| `wanderbot-web` | `ui/Dockerfile` | React SPA via Nginx on :8080 (proxies `/api` → API) |
| `wanderbot-mcp` | `Dockerfile.mcp` | Standalone MCP tool server on :8090 |

State lives in **Postgres** (app store + LangGraph checkpointer) and **Redis** (rate limiting / KEDA).

---

## 1. Run the whole stack locally (Docker Compose)

```bash
cp .env.example .env      # fill in provider keys (Duffel, Tavily, Google/OpenAI…)
docker compose up --build
# UI:  http://localhost:8080   (proxies /api to the backend)
# API: http://localhost:8080/api/healthz
```

Compose runs `app` + `web` + `postgres` (pgvector) + `redis`. The app uses Postgres for
both the checkpointer (`WB_DATABASE_URL`) and the app store (`WB_APP_STORE_URL`).

---

## 2. Configuration & secrets

App config is 12-factor via `WB_`-prefixed env vars (see `.env.example`).

**Required in production** (synced from the secrets manager via External Secrets):

| Var | Purpose |
|-----|---------|
| `WB_APP_STORE_URL` | Postgres URL for users/plans/chats (**must** be set in prod — the API runs read-only, SQLite can't write) |
| `WB_DATABASE_URL` | Postgres URL for the LangGraph checkpointer |
| `WB_REDIS_URL` | Redis URL |
| `WB_JWT_SECRET` | ≥32-char signing secret |
| Provider keys | `WB_DUFFEL_API_KEY`, `WB_TAVILY_API_KEY`, `WB_OPENAI_API_KEY` / `WB_GOOGLE_API_KEY`, AWS creds for Bedrock guardrails |

> If `WB_APP_STORE_URL` is unset, the app store falls back to SQLite (dev only).

---

## 3. CI/CD (GitHub Actions)

- **CI** (`.github/workflows/ci.yml`) on every PR: frontend type-check + build; backend ruff/mypy/pytest.
- **CD** (`.github/workflows/deploy.yml`) on push to `main` / `v*` tags:
  1. Build & push `wanderbot-api`, `wanderbot-web`, `wanderbot-mcp` to GHCR.
  2. Trivy scans the API image (fails on CRITICAL/HIGH).
  3. `helm upgrade` to **staging** (`wanderbot-staging` namespace).
  4. `helm upgrade` to **production** — gated by the `production` GitHub Environment
     (manual approval); `--atomic` auto-rolls-back on failed health checks.

---

## 4. Manual Helm deploy

```bash
helm upgrade --install wanderbot deploy/helm/wanderbot \
  -f deploy/helm/wanderbot/values-prod.yaml \
  --set image.tag=<git-sha> \
  --namespace wanderbot --create-namespace --atomic --wait
```

The chart deploys `api`, `web`, and `mcp` Deployments + Services, an HPA on the API,
a NetworkPolicy, and an Ingress that routes `/api`, `/healthz`, `/metrics` → API and
everything else → the SPA. TLS via the `wanderbot-tls` secret; secrets via
External Secrets Operator (`wanderbot/prod` path).

Verify:

```bash
kubectl -n wanderbot rollout status deploy/wanderbot-api deploy/wanderbot-web
curl -fsS https://<host>/healthz
```

Rollback: see [`rollback.md`](./rollback.md) (`helm rollback wanderbot`).

---

## 5. Database

App tables (`users`, `plans`, `chat_threads`) are created on first boot
(`storage/db.py`). For a managed Postgres, point `WB_APP_STORE_URL` /
`WB_DATABASE_URL` at it and ensure the `vector` extension is available for the
checkpointer/RAG store. No manual migration step is required for the app store.
