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
- [ ] OpenRouter call failures (timeout, rate limit, malformed response) → graceful message to
      user, not a raw 500
- [ ] Basic response length cap / max token limit — protects the $5 budget from a runaway
      response or adversarial input
- [ ] Redeploy, confirm the live URL still works after all changes

## Phase 6 — Adversarial test pass (target: 20 min)
Run these manually against the live URL before calling it done:
- [ ] A question just outside KB scope → should escalate gracefully, not hallucinate
- [ ] A direct pricing question (not in KB) → should deflect appropriately, not invent a number
- [ ] An off-topic/hostile message → should stay on-brand and redirect
- [ ] One happy-path question from each of the 6 scenarios in the brief → confirm all work
- [ ] Log any real bugs found + fixes in DECISIONS.md (needed for Code Deep Dive review section)

## Phase 7 — Wrap-up (target: 10 min)
- [ ] Final commit + push
- [ ] Update DECISIONS.md: model chosen, any scope cut under time pressure, any known bugs left
- [ ] Confirm README has set up + local run instructions
- [ ] Confirm live URL works from a fresh/incognito browser session (not just localhost)

---

## Explicitly cut from this build (state these plainly, don't leave ambiguous)
- Client portal auth/functionality — link/explanation only
- Persistent chat history / accounts
- Vector DB / RAG — static KB injection instead (see DECISIONS.md)
- Postgres / structured lead storage — stdout logging instead
- Deployed K8s/autoscaling — reference-only, not part of this deploy
- Automated test suite — manual adversarial pass only, given the time budget

## If time remains after Phase 7
- Postgres for escalation/lead capture instead of stdout logging
- Token usage / cost-per-conversation logging (ties to telemetry discussion in review)
- `k8s/` reference folder with example Deployment + HPA manifests, clearly marked not-deployed
