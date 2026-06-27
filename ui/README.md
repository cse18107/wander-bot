# Wanderbot UI

React + Vite + TypeScript frontend for the holiday planner.

## Features
- Streaming chat that drives the multi-agent `/api/plan` graph (SSE over fetch).
- Live **itinerary panel**: flight/hotel/activity cards, day-by-day plan, running budget bar (green within budget, red over).
- **Approval modal** wired to the human-in-the-loop pause — nothing reserves until you approve.
- **Preferences** panel showing learned long-term memories, with a "Forget" (privacy) action.

## Run

```bash
# 1) start the API (from repo root)
uvicorn wanderbot.api.main:app --reload

# 2) start the UI
cd ui
npm install
npm run dev        # http://localhost:5173 (proxies /api -> :8000)
```

## Notes
- SSE endpoints are POST, so the client reads the streamed body and parses
  `event:`/`data:` frames itself (see `src/api.ts`) rather than using `EventSource`.
- Event names match the backend: `step`, `selections`, `budget`, `itinerary`,
  `message`, `approval_required`, `done`, `error`.
