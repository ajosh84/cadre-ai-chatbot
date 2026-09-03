# Cadre AI Support Chatbot

A customer support chatbot for Cadre AI, an AI strategy and implementation consultancy. Handles
common inbound questions (services, industry fit, booking a call, client portal, the AI
Maturity Index, LLM/data security approach) and escalates to a human for anything outside that
scope. See `CLAUDE.md` for full project context, `plan.md` for build phases, and `DECISIONS.md`
for the reasoning behind each non-obvious choice.

## Setup

Requires [Poetry](https://python-poetry.org/) and Python 3.12+.

```bash
poetry install
```

Copy `.env.example` to `.env` and fill in your OpenRouter API key:

```bash
cp .env.example .env
```

```
OPENROUTER_API_KEY=your-key-here
```

## Running locally

```bash
poetry run uvicorn backend.app:app --reload --port 8000
```

Run this from the project root, not `backend/` — `backend/app.py` imports the knowledge base as
`from backend.prompts import SYSTEM_PROMPT`, which needs the repo root on the Python path.

Then open http://127.0.0.1:8000 in a browser for the chat UI, or check http://127.0.0.1:8000/health.

## Running tests

```bash
poetry run pytest --html=report.html --self-contained-html
```

Runs the full test suite (`tests/test_app.py`) and writes a browsable report to `report.html`
at the project root — open it directly in a browser, nothing to serve. Every OpenRouter call is
mocked, so the suite runs offline and doesn't touch the API budget.

## Project structure

- `backend/app.py` — FastAPI app: routes, OpenRouter integration, escalation logging
- `backend/prompts.py` — system prompt and knowledge base content
- `frontend/index.html` — chat UI (vanilla HTML/CSS/JS, no build step)
- `tests/test_app.py` — automated test suite (routes, request shaping, failure handling,
  escalation detection) — see "Running tests" above
- `.env.example` — required environment variables

## Known Limitations

- Conversation history is capped at the last 5 exchanges (no long-term memory).
- Escalation detection uses heuristic phrase-matching, not a classifier.
- No persistent lead storage — escalations are logged to stdout only.
- See DECISIONS.md for full reasoning behind these choices and trade-offs considered.