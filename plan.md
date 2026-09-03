# plan.md

Build plan for the Cadre AI support chatbot. Total budget: ~4 hours. Phases are mostly
sequential — later phases depend on earlier ones working, so don't parallelize the core path.
Two independent side-tasks are marked as subagent candidates.

## Phase 0 — Setup (target: 15 min)
- [x] Repo init, `.gitignore` (`.env`, `__pycache__`, etc.)
- [x] `CLAUDE.md`, `plan.md`, `DECISIONS.md` committed first, before any app code
- [x] Add real dependencies to pyproject.toml: fastapi, uvicorn[standard], httpx, python-dotenv
      — run `poetry add fastapi "uvicorn[standard]" httpx python-dotenv`
- [x] `.env.example` with OPENROUTER_API_KEY= placeholder
## Phase 1 — Scaffold + deploy skeleton (target: 30 min)
- [x] Minimal FastAPI app: one `GET /` route serving a static `index.html` placeholder, one
      `GET /health` route
- [x] Push to GitHub, connect to Railway/Render, get a live public URL working end-to-end
      **before** building real functionality — this is the "deploy early" step, do not skip it
- [x] Confirm env var (`OPENROUTER_API_KEY`) is set correctly on the platform

## Phase 2 — Core chat endpoint (target: 40 min)
- [x] `POST /api/chat` — accepts a user message (+ minimal conversation history), calls
      OpenRouter async via `httpx`/SDK, returns the response
- [x] System prompt + KB content wired in from `backend/prompts.py` (see DECISIONS.md for what
      goes in the KB — company overview, booking, portal, AI Maturity Index, LLM/data security
      approach, escalation instruction)
- [x] Test with curl/httpie before touching the frontend — confirm the model is grounding
      answers in the KB and not hallucinating
- [x] Pick and lock in the OpenRouter model (cheap/fast — see DECISIONS.md open question),
      log the decision once made

## Phase 3 — Frontend (target: 45 min) — SUBAGENT CANDIDATE
Independent of Phase 2's internals once the `/api/chat` contract is defined (request/response
shape) — a subagent can build the static HTML/CSS/JS chat UI in parallel with backend work,
as long as the API contract is agreed first.
- [x] Simple chat UI: message list, input box, send button
- [x] Wire to `/api/chat` — built as single request/response, not SSE (see note below)
- [x] Basic loading state, basic error state (see Phase 5)
- [x] Cadre-appropriate styling — clean, professional, B2B — not elaborate

## Phase 4 — Escalation flow (target: 30 min)
- [x] System prompt instructs the model: when a question falls outside the provided KB, say so
      explicitly and ask for name/email (or point to a contact method) instead of guessing
- [x] Simple contact capture: log escalated conversations (stdout is fine for MVP — visible in
      platform logs). Note in DECISIONS.md this is where Postgres would go next.
- [x] Test explicitly: ask something clearly out of scope, confirm it escalates instead of
      making something up

## Phase 5 — Error handling + hardening (target: 30 min) — SUBAGENT CANDIDATE
Can run somewhat independently once Phase 2's endpoint exists — a subagent can focus purely on
failure modes while the main thread polishes the frontend.
- [x] OpenRouter call failures (timeout, rate limit, malformed response) → graceful message to
      user, not a raw 500
- [x] Basic response length cap / max token limit — protects the $5 budget from a runaway
      response or adversarial input
- [x] Basic input validation on incoming message length (added, not originally listed here —
      see below)
- [x] Cap on conversation history sent to OpenRouter per request (last 10 messages / 5
      exchanges) — added, not originally listed here; frontend still keeps the full thread for
      display. See DECISIONS.md.
- [x] Redeploy, confirm the live URL still works after all changes

## Phase 6 — Adversarial test pass (target: 20 min)
Run these manually against the live URL before calling it done:
- [x] A question just outside KB scope → should escalate gracefully, not hallucinate
- [x] A direct pricing question (not in KB) → should deflect appropriately, not invent a number
- [x] An off-topic/hostile message → should stay on-brand and redirect
- [x] One happy-path question from each of the 6 scenarios in the brief → confirm all work
- [x] Log any real bugs found + fixes in DECISIONS.md (needed for Code Deep Dive review section)

Run against the **local** server (`poetry run uvicorn backend.app:app --reload --port 8000`),
Also went further than the four items above: full exhaustive pass across 6 brief scenarios, out-of-scope/escalation (pricing, fabricated
client, account-modification request), 3 prompt-injection attempts, 4 edge cases (empty,
oversized, non-English, emoji/gibberish), a 4-turn history conversation, and 2 hostile-tone
messages — 23 requests total, all reviewed for hallucination/leakage/tone/crashes, one real bug
found and fixed (see DECISIONS.md).

## Phase 7 — Wrap-up (target: 10 min)
- [x] Final commit + push — **not done by Claude**, per the new "Git discipline" rule in
      CLAUDE.md: the developer stages/commits/pushes personally. Claude will suggest a commit
      message when asked.
- [x] Update DECISIONS.md: model chosen, any scope cut under time pressure, any known bugs left
- [x] Confirm README has set up + local run instructions — `README.md` created (didn't exist
      before), instructions verified against a real local run
- [x] Confirm live URL works from a fresh/incognito browser session (not just localhost) — not
      verifiable from here: no browser-automation tool is connected in this environment, and
      Claude doesn't have the deployed URL. Developer should confirm this manually.

## Phase 8 — Automated test suite (target: 30-40 min)
Originally cut from the build (see "Explicitly cut" below) in favor of a manual adversarial
pass under the 4-hour budget; revisited now that the MVP is stable. This reverses that scope
cut — plan.md and DECISIONS.md get updated once it's done to reflect that explicitly, not just
silently un-cut.

- [x] Add `pytest` as a dev dependency: `poetry add --group dev pytest`. No other new
      dependencies needed — FastAPI's `TestClient` (bundled with `fastapi`/`starlette`, backed
      by `httpx`, already a dependency) covers HTTP-level testing, and `unittest.mock` (stdlib)
      covers mocking the OpenRouter call. No `pytest-asyncio` or separate HTTP-mocking library
      needed at this scope. `TestClient` is Starlette's test client (FastAPI re-exports it), so
      every route/mock test below runs through the real ASGI app, not a hand-rolled stub.
- [x] Also add `pytest-html` as a dev dependency (same command:
      `poetry add --group dev pytest pytest-html`) — generates the human-readable test report
      requested below. This is the one dependency addition in this phase beyond pytest itself;
      justified because the report is an explicit deliverable, not incidental tooling.
- [x] `tests/test_app.py` — single file for now, mirrors `backend/app.py`'s own "don't pre-split"
      convention; split only if it actually grows. 26 tests total.
- [x] Route-level tests (`GET /`, `GET /health`):
  - `GET /health` → 200, `{"status": "ok"}`
  - `GET /` → 200, serves `frontend/index.html`'s actual content
- [x] `POST /api/chat` input validation tests — assert via mock call count that no OpenRouter
      call happens for any rejected request:
  - missing `message` field → 422
  - empty `message` (`""`) → 422
  - `message` over `MAX_MESSAGE_LENGTH` (2000 chars) → 422
  - `message` exactly at the 2000-char boundary → accepted (200, mocked OpenRouter response)
  - missing `history` field → defaults to `[]`, request still succeeds
- [x] `POST /api/chat` request-shaping tests — mock the OpenRouter call, capture and assert on
      the outgoing request payload:
  - system message (`SYSTEM_PROMPT`) is always first in `messages`
  - `history` entries are forwarded in order between the system message and the new user message
  - `history` longer than `MAX_HISTORY_MESSAGES` (10) is trimmed to the last 10 entries only
  - `max_tokens` is set to `MAX_RESPONSE_TOKENS` (500) on every request
- [x] `POST /api/chat` happy-path test — mock a normal OpenRouter completion, assert the response
      body is exactly `{"response": "<the mocked content>"}`
- [x] `POST /api/chat` failure-handling tests — each should return `200` with a graceful message,
      never a raw 500:
  - mocked `httpx.TimeoutException` → graceful apology response
  - mocked `httpx.HTTPStatusError` (e.g. a 401 or 429 from OpenRouter) → graceful apology
    response
  - mocked malformed OpenRouter response body (missing `choices` key) → graceful apology
    response, confirms the `KeyError`/`IndexError` guard works
  - `OPENROUTER_API_KEY` unset/empty → graceful config-error message, and assert the OpenRouter
    call was never attempted
- [x] `log_if_escalation()` unit tests — pure function, no HTTP mocking needed, use `capsys` to
      assert on stdout:
  - each marker in `ESCALATION_MARKERS` individually triggers a log line, in a reply that
    otherwise looks like a real model response
  - a normal in-scope-sounding reply with none of the markers → no log line
  - a reply containing newlines → logged as a single flattened line (no literal newline breaking
    grep-ability)
  - the logged line's user-message and reply portions match `message`/`reply` exactly (minus the
    newline flattening)
  - **Found a real bug this way**: the `"I don't have"` marker (capital I) could never match
    against the always-lowercased comparison string — dead since Phase 6. Fixed to
    `"i don't have"`. See DECISIONS.md.
- [x] Run `poetry run pytest --html=report.html --self-contained-html`, confirm all tests pass,
      and confirm no test makes a real OpenRouter call — verify by running once with a
      deliberately broken/missing API key; every test should still pass, since every OpenRouter
      interaction is mocked. `--self-contained-html` embeds the CSS/JS inline so `report.html`
      is a single portable file — open it directly in a browser, nothing to serve.
  - **Not originally planned**: needed a `[tool.pytest.ini_options]` `pythonpath = ["."]` entry
    in `pyproject.toml` — without it, pytest's default import mode (no `tests/__init__.py`) puts
    `tests/` rather than the repo root on `sys.path`, so `from backend...` imports failed with
    `ModuleNotFoundError`. One-line fix, same root cause pattern as the Phase 1/2 import bug.
  - Result: **26 passed**, 0 failed (after the marker fix above), 1 warning (Starlette's
    deprecation notice for `httpx`-backed `TestClient`, recommending `httpx2` — informational
    only, not acted on; would need its own dependency evaluation if `httpx`-backed `TestClient`
    is ever actually removed).
- [x] Add `report.html` (and pytest's `.pytest_cache/`) to `.gitignore` — generated artifacts,
      regenerated on every run, not committed.
- [x] Update `README.md` with a "Running tests" section: the pytest command above, and that it
      opens as `report.html` at the project root.
- [x] Update `DECISIONS.md`: logged as reversing the earlier "no automated test suite" scope
      cut, with reasoning, plus the case-sensitivity bug found via the suite.
- [x] Updated this file's "Explicitly cut" list below to reflect that the test suite was
      revisited in Phase 8, rather than leaving a stale "cut" note.

Not committed — per the "Git discipline" rule in CLAUDE.md, staging/committing is left to the
developer.

---

## Explicitly cut from this build (state these plainly, don't leave ambiguous)
- Client portal auth/functionality — link/explanation only
- Persistent chat history / accounts
- Vector DB / RAG — static KB injection instead (see DECISIONS.md)
- Postgres / structured lead storage — stdout logging instead
- Deployed K8s/autoscaling — reference-only, not part of this deploy
- Automated test suite — originally cut in favor of a manual adversarial pass given the time
  budget; revisited in Phase 8 once the MVP was stable (see above)

## If time remains after Phase 7
- Postgres for escalation/lead capture instead of stdout logging
- Token usage / cost-per-conversation logging (ties to telemetry discussion in review)
- `k8s/` reference folder with example Deployment + HPA manifests, clearly marked not-deployed
