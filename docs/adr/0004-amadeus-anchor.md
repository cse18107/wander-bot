# ADR-0004: Anchor flights/hotels/activities on Amadeus Self-Service

**Status:** Accepted

## Context
"No mocks" requires real provider data from day one, across three hard domains,
without commercial onboarding or spend during development.

## Decision
Anchor flights, hotels, and activities on the **Amadeus Self-Service** suite: one
OAuth2 credential, one error model, and a free **test environment with real-shaped
data**. Each domain sits behind a `Provider` interface so any single one can be
swapped to a specialist (Duffel for ticketing, Hotelbeds for wholesale, Viator).

## Consequences
- Pro: least integration surface; promotion to prod = base URL + credentials.
- Pro: real data in tests/CI via the sandbox; `vcrpy` cassettes for determinism.
- Con: vendor coupling for v1; mitigated by the provider interface.
