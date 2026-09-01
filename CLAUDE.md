# CLAUDE.md

## Project

A customer support chatbot for Cadre AI, an AI strategy and implementation consultancy.
The bot handles common inbound inquiries from prospective clients, existing clients, and
people learning about the company, so the human inbound team can focus on high-value
conversations. This is a scoped MVP built under a 4-hour time budget — not a production system.

Cadre AI: AI strategy, workflow automation, AI agents, and leadership facilitation for B2B
companies (professional services, private equity, financial services, real estate,
construction, manufacturing, retail, and more). Core services: AI Strategy, AI Leadership &
Facilitation, AI Engineering, AI Agents.

## Tech stack

- **Backend**: FastAPI (Python), async routes, `asyncio` throughout
- **Frontend**: Plain HTML/CSS/vanilla JS, served as static files by FastAPI. No frontend
  framework, no separate frontend build/deploy.
- **Model access**: OpenRouter (single API key, provided, $5 budget, 7-day expiry). This key
  powers the deployed chatbot's responses ONLY — never use it for anything else.
- **Deployment**: Single service on Railway or Render. One deploy target, one public URL.
- **No database in v1.** Escalation/lead capture logs to stdout (visible in platform logs) for
  the MVP. See plan.md for the Postgres upgrade path if time allows.
- **No vector DB / RAG.** Knowledge base is a small, static, structured file
  (`backend/knowledge_base.py` or `.md`) injected directly into the system prompt. The KB is
  small enough (roughly a page) that retrieval infrastructure would be unjustified complexity.
  See DECISIONS.md for the full reasoning —  can introduce ChromaDB/embeddings/vector search
  after discussing based on expansion scope.

## Conventions

- Env vars via `.env` (never commit it — `.gitignore` already covers this). Required:
  `OPENROUTER_API_KEY`.
- Routes live in `backend/app.py` (or split into `backend/routes/` only if it actually grows —
  don't pre-split for a 2-endpoint app).
- System prompt + KB content are separate from route logic — keep them in their own module
  (`backend/prompts.py` or similar) so they're easy to find and edit independently of request
  handling.
- `/api/chat` returns a single JSON response (not SSE streaming) — a deliberate scope trade-off
  for the time budget, not a rejection of streaming on principle. See DECISIONS.md.
- Prefer small, focused commits with descriptive messages over one large commit at the end.

## Explicit boundaries — do not build these without asking

- No client portal / auth / login functionality. The bot explains what the portal is and gives
  a link — it does not implement portal features.
- No persistent chat history across sessions or user accounts.
- No admin dashboard.
- No vector DB, embeddings, or RAG pipeline (see above).
- No Kubernetes / autoscaling infra actually deployed. A reference-only `k8s/` folder may exist
  for discussion purposes but nothing in it should be part of the deploy path.
- Don't add new dependencies without a clear reason — this is a small app, keep it small.

## Decisions already made (don't relitigate mid-build)

- FastAPI + vanilla JS frontend in one app, one deploy — chosen for speed and because it's a
  stack the developer already has production experience in. See DECISIONS.md.
- Model for the chatbot itself: cheap, fast model via OpenRouter (confirm choice in
  DECISIONS.md once picked) — budget is limited ($5) and needs to last through a live review.
- Escalation is handled via system-prompt instruction (model says "I don't know, here's how to
  reach a human"), not a separate intent-classification call. Simpler, one fewer moving part.

## How to run locally

```bash
poetry install
poetry run uvicorn backend.app:app --reload --port 8000
```
Run from the project root (not `backend/`) — `backend/app.py` imports the knowledge base as
`from backend.prompts import SYSTEM_PROMPT`, which needs the repo root on the Python path.
Requires `.env` with `OPENROUTER_API_KEY` set.

## Full context

See `plan.md` for build phases and `DECISIONS.md` for the reasoning behind every non-obvious
choice above — both are meant to be read together with this file, not duplicated in it.
