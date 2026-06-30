# Runbook: Rollback

## When to roll back
- Failed health/readiness after a deploy, error-budget burn, or a red-team/eval gate
  regression that reached prod.

## Automatic
Production `helm upgrade` uses `--atomic --wait`, which **auto-rolls-back** on failed
health checks. No action needed if the deploy never went healthy.

## Manual
```bash
# inspect history
helm history wanderbot -n wanderbot
# roll back to the previous good revision
helm rollback wanderbot <REVISION> -n wanderbot --wait
```

## Safety notes
- Conversations are checkpointed (Postgres), so rolling pods do **not** lose in-flight
  plans — a resumed run continues on any replica.
- Roll back the API and MCP images **together** (same tag) to avoid contract skew.
- If a DB migration shipped with the bad release, roll the schema back *before* the
  app, or use the expand/contract pattern to keep the old app compatible.
