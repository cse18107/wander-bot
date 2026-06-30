# ADR-0005: AWS Bedrock Guardrails as the primary detector

**Status:** Accepted

## Context
Hand-rolled regex guardrails are evadable and not production-grade as a primary
defense. Market options exist (Bedrock, NeMo, Lakera, Llama Guard).

## Decision
Use **AWS Bedrock Guardrails** (`ApplyGuardrail`) as the authoritative detector
behind a pluggable engine (`security/engine.py`). Keep the regex layer as a **cheap
pre-filter and offline/CI fallback**. Selection is config-driven
(`WB_GUARDRAILS_BACKEND`); any AWS error fails safe to regex.

Bedrock covers prompt-attack, content filters, denied topics, PII, word filters,
and contextual grounding (anti-hallucination). Tool authorization remains
**structural** (the tool-arg rail), since Bedrock classifies content but does not
authorize actions.

## Consequences
- Pro: managed, multilingual, maintained detection; standardizes on AWS.
- Pro: regex pre-filter blocks the obvious for free, limiting Bedrock cost.
- Con: per-call cost and an AWS dependency; mitigated by pre-filter + fallback.
