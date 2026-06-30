# Runbook: Incident response

## Severity
- **SEV1** — API down or guardrails bypassed (safety). Page on-call immediately.
- **SEV2** — degraded (a provider down, elevated errors/latency).
- **SEV3** — minor (single non-critical feature impaired).

## First 5 minutes
1. Check `/healthz` and the Grafana dashboard (latency, error rate, cost, guardrail
   block rate).
2. Look at LangSmith traces for the failing `thread_id`; every run carries
   `user_id`/`thread_id`/`agent`/`tool`.
3. Identify blast radius: one provider (Amadeus/Tavily/Bedrock) or systemic?

## Common scenarios
- **Provider outage (Amadeus/Tavily):** errors surface as retryable `ProviderError`;
  the graph degrades (skips that step) rather than failing. Confirm circuit-breaker
  behavior; no action unless error budget burning.
- **Guardrail/Bedrock unavailable:** engine fails safe to regex (logged
  `bedrock_guardrail_fallback`). Safety maintained at reduced fidelity; restore AWS.
- **Cost spike:** check `wb_llm_cost_usd_total`; the per-request budget guard should
  abort runaway loops. If sustained, lower `WB_REQUEST_COST_BUDGET_USD`.
- **Rate-limit complaints:** verify Redis health (limiter falls back to in-process,
  which is per-replica and stricter under load).

## Comms
Post status in the incident channel every 15 min (SEV1/2). Record timeline for the
postmortem.

## Postmortem
Blameless. Capture: timeline, root cause, detection gap, and 2–3 concrete
preventions (e.g., a new red-team case or eval).
