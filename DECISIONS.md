[# Decisions Log — Cadre AI Chatbot Take-Home

Running record of architecture, scope, and stack decisions, with reasoning.
Purpose: (1) keep the build honest to what was actually decided and why, (2) serve as prep
material for the review, especially the "Decisions & Trade-offs" (10%) and "Architecture" (25%)
sections.

Update this as you go — each entry should capture the decision, the alternative(s) considered,
and why this one won.
---

## Stack

**Decision:** FastAPI (Python) + asyncio, serving a minimal static/Jinja2 frontend (HTML/CSS/vanilla JS)
from the same app. Single deployment target.

**Alternatives considered:**
- Next.js — stack-agnostic "safe default," but I do not have real reps in it. Would mean
  learning a framework, building the app, at once under a 4–6 hr budget. 
  Rejected: familiarity > theoretical stack fit for a time-boxed build.
- FastAPI backend + separate frontend (two deploys) — more "standard" architecture, but adds
  CORS config and a second deploy surface, both real risk under time pressure. Rejected in favor
  of single-deploy simplicity; not a capability gap, a scope call.

**Why this wins:** I have engineering experience incl. production FastAPI +
asyncio work (Wiser Solutions: FastAPI/NATS/Redis/Postgres/K8s streaming pipeline). Single
deploy = fewer failure points during the "deploy early" phase and no CORS surface area.

---

## Deployment

**Decision:** Railway or Render (single Python service), free/cheap tier. Public HTTPS URL.

**Alternatives considered:**
- AWS from scratch (ECS/EKS, RDS, ALB, etc.) — rejected. Real infra setup time for a workload
  that will see trivial demo traffic; risks eating the whole time budget on plumbing instead of
  the actual chatbot. Directly contradicts the guide's own scope-discipline scoring criteria.
- Full Kubernetes deployment with HPA/autoscaling — rejected as *deployed* infra for the same
  reason: no real load to justify it, real cost/time to stand up a cluster, and over-engineering
  reads as a scope-judgment miss (20% of score is speed & scope discipline).

**Compromise:** Include a `k8s/` reference folder in the repo (Deployment + HPA manifests)
explicitly labeled "not deployed — reference architecture for production scale," written using
real K8s/AWS knowledge but without burning build hours or violating the challenge's own scope
guidance. Gives a concrete artifact to walk through live in the review without paying the cost
of actually running it.

---

## System Design — v1 (what's actually built)

- Direct async request → OpenRouter call → single JSON response (not SSE — see "Streaming vs.
  single response" below), no queue.
- Static system-prompt + KB content injected per request (no vector DB / RAG infra).
  Rationale: KB is small (one company's FAQ-level content); embeddings/retrieval
  infra would be over-engineering at this scale, not a strength.
- Escalation path: when the bot can't confidently answer from the KB, it says so
  explicitly and captures contact info instead of guessing. This is the one place scope
  was *intentionally* pushed a bit further than minimum, since hallucination control
  
## System Design — v2 ("how would we scale this")

1. **At current scale:** connection pooling, streaming responses,
   maybe a lightweight queue (Postgres-as-queue) purely for backpressure against
   OpenRouter rate limits. No infra changes needed for realistic Cadre inbound volume.
2. **Real production architecture (drawing on actual Wiser Solutions
   experience, not hypothetical):**
   - Frontend server holds a unidirectional stream (SSE/WebSocket) per user.
   - Request + correlation ID + context published to a NATS **subject** ( — dot-hierarchical, e.g. `chat.requests.new`, wildcards `*` / `>`).
   - Async consumer pool picks up requests, calls out to the model layer, with
     exponential backoff for rate limiting.
   - Postgres as system-of-record for durability/audit/replay — distinct purpose from
     NATS (queue vs. durable log), stated explicitly so it doesn't read as two
     competing queue mechanisms.
   - Responses routed back to the correct open connection via the correlation ID
     
3. **About using self-hosted model serving (vLLM, continuous batching,
   KV-cache, KEDA-(kubernetes event driven) based autoscaling on K8s):** reason from first principles precisely,
   Batching only makes sense once we're hosting your own weights — doesn't apply to OpenRouter calls
4. **Explicit tradeoff:** self-hosting (vLLM) vs. hosted API
   (OpenRouter) is a cost/control tradeoff, not a strict upgrade. Only justified once
   volume/unit economics demand it — for Cadre's actual inbound bot traffic, direct
   OpenRouter calls are almost certainly correct for a long time.

---

## Scope — explicitly in

1. What Cadre does / whether it works with the user's industry
2. How to book a strategy call
3. What the AI Maturity Index is / how to get scored
4. LLM selection & data security approach (grounded from KB)
5. Escalation flow with contact capture for anything else

## Scope — explicitly out (and why)

- **Client portal (login, tracking AI tools/results):** this is a real authenticated app,
  not a chatbot feature. Bot explains what the portal is + gives a link/contact,
  does not attempt to build portal functionality. Named explicitly as a scope
  boundary, not an oversight.
- **Persistent chat history across sessions / accounts:** out of scope for MVP.
- **Admin dashboard:** out of scope for MVP; eval approach can be discussed verbally.
- **Vector DB / RAG infra:** not needed at current KB size; noted as the first
  thing to add if KB scope grows materially.
- **Deployed K8s/autoscaling:** see Deployment section above — built as reference
  only, not deployed.

---

## Open questions / to revisit

- [x] Model choice for the chatbot itself (cost/quality tradeoff) — decide and log
      reasoning here once picked.
- [x] Whether to add Postgres for lead capture in v1, or keep it to logging only. **Resolved:
      logging only.** Kept to stdout for the full build (see "Escalation / contact-capture
      logging" above) — no time pressure forced this either way, it was the right scope call
      from the start given the $5/4-hour budget and that stdout is already visible in
      Railway/Render's platform logs. Postgres remains the documented next step if lead volume
      or the need for structured querying grows (see plan.md's "If time remains" list).
- [x] Two or three specific real examples of Claude Code getting something wrong
      during the actual build, and how I caught/fixed it (needed for Code Deep
      Dive section) — see "Bugs found during the build" below.

## Model choice
**Decision:** `openai/gpt-4o-mini` via OpenRouter.
**Why:** Cheapest reliable option ($0.15/$0.60 per million tokens input/output) vs.
Claude Haiku 4.5 ($1/$5) — meaningful difference given the fixed $5/7-day budget.
Free-tier models considered and rejected: this bot is client-facing and needs consistent
instruction-following (grounding, escalation behavior), which is worth paying a small
amount for over free models with less predictable behavior.

---

## Verification — Phase 2 manual test pass

Tested via curl: 6 in-scope questions, 3 out-of-scope/escalation questions, 2 adversarial
(prompt injection attempt, hostile tone), 1 multi-turn context check. All behaved correctly —
grounded answers matched KB, escalation triggered on unknown/pricing questions without
hallucinating, multi-turn history was used correctly, adversarial attempts did not break
character or leak instructions.

Also caught and fixed during this phase: `backend/app.py` initially imported
`from prompts import SYSTEM_PROMPT` (module-not-found error) instead of
`from backend.prompts import SYSTEM_PROMPT` — gave Claude Code the exact traceback,
it corrected the import path immediately.

## Streaming vs. single response
**Decision:** /api/chat returns a single JSON response, not SSE streaming.
**Why:** CLAUDE.md originally specified SSE as a convention; plan.md's Phase 3 explicitly
allowed falling back to single-response "if streaming eats too much time" — it did, given
the 4-hour budget. A typing indicator provides adequate perceived responsiveness without
the added complexity of chunked streaming on both backend and frontend. This is a
deliberate scope cut, not an oversight — SSE would be the first UX improvement to add
with more time.

## Escalation / contact-capture logging (Phase 4)
**Decision:** Detect escalation heuristically — check the model's reply for the escalation
wording from `SYSTEM_PROMPT` ("don't have that information", "name and email") — and print a
single structured line (`ESCALATION: user asked '...' | response: '...'`) to stdout, grep-able
out of Railway/Render logs.
**Alternatives considered:** A separate classification call to detect escalation more reliably
— rejected per the standing decision in CLAUDE.md to keep escalation a system-prompt instruction
rather than a second model call; a substring check on the response the model already produced is
"free" and consistent with that choice.
**Why this wins:** No DB in v1 (see CLAUDE.md) — stdout is the lead-capture record for now.
**Next step if this grows:** Postgres table for escalated conversations (message, reply,
timestamp) so leads aren't only recoverable via log search.

**Purpose and failure-mode priority:** This log is Cadre's follow-up queue of real leads the bot
couldn't fully serve — every missed detection is a real prospective or existing client whose
question never reaches a human. That makes under-detection (missing a genuine escalation) a more
serious failure than over-detection (flagging something as an escalation when it wasn't quite
one): a few extra lines in the log cost nothing to skim past, but a missed lead is gone. The
marker set was broadened for exactly this reason after testing surfaced real cases the narrower
original set missed — e.g. "Do you have any experience working with healthcare companies
specifically on HIPAA compliance audits?" (model said "I can't confirm...") and "Can I speak to
a specific person named John Smith on your team?" (model said "I'm unable to connect you
directly...") — neither matched the original two markers, which were tied too tightly to the
system prompt's primary phrasing rather than the range of ways the model actually declines.
`ESCALATION_MARKERS` in `backend/app.py` now also covers "cannot provide", "can't confirm",
"unable to provide", "I don't have", and "reaching out to the team".

## Conversation history cap (Phase 5 hardening)

**Decision:** `/api/chat` only forwards the last `MAX_HISTORY_MESSAGES = 10` entries of
`history` (5 user/assistant exchanges) to OpenRouter, regardless of how long the client-side
`history` array has grown. The frontend still keeps and renders the full thread — this is a
server-side trim of what gets sent per request, not a UI limitation.

**Why:** The Phase 5 message-length cap only bounded the *new* incoming message; `history` was
still unbounded and resent in full on every turn, so cost grows linearly with conversation
length and a long-running conversation could eventually exceed the model's context window.
Capping at 10 is a fixed, cheap guard against both.

**Verification:** Built a synthetic 14-message history with a distinct fact planted in the
dropped range (indices 0–1, outside the last 10) and another in the kept range (indices 6–7,
inside it). The model correctly forgot the dropped fact and correctly recalled the kept one,
confirming the trim behaves as intended without breaking normal multi-turn context for
conversations under the cap.

**Trade-off:** A real conversation that leans on something said more than 5 exchanges back will
lose that context — acceptable for this bot's short, FAQ-style support conversations.

**Next step if this grows:** Currently, history is capped by keeping the last N turns — simple,
zero added infra. With more time, I'd replace this with actual compaction: periodically
summarizing older turns using a lightweight dedicated summarization model like BART (rather than
spending a full chat-model call just to compress context), keeping token cost down while
preserving the gist of earlier conversation. I've built this pattern before — BART/FlanT5 for
summarization in a RAG pipeline — so this isn't hypothetical, it's the natural next step if
conversation length in production warranted it.

---

## Bugs found during the build (pre-Phase 6)

Consolidated here per plan.md Phase 6's "log any real bugs found" requirement, ahead of the
adversarial test pass (which will surface any additional issues in `backend/app.py`'s actual
chat behavior). The first two are also the "Claude Code getting something wrong" examples noted
in Open Questions above.

1. **Import path bug (Phase 1/2).** `backend/app.py` initially imported
   `from prompts import SYSTEM_PROMPT`, which only resolves when uvicorn is launched from inside
   `backend/`. Running the documented `poetry run uvicorn backend.app:app --reload --port 8000`
   from the repo root failed with `ModuleNotFoundError: No module named 'prompts'`. Caught by
   actually running the app and reading the traceback (not by inspection). Fixed to
   `from backend.prompts import SYSTEM_PROMPT`, added `backend/__init__.py` to make `backend`
   an explicit package, and corrected CLAUDE.md's "How to run locally" section, which had also
   drifted — it still referenced `pip`/`uv sync`, not the Poetry setup actually in use.

2. **Escalation detection under-coverage (Phase 4).** The initial `ESCALATION_MARKERS` list
   (`"don't have that information"`, `"name and email"`) missed real escalation cases where the
   model declined in different wording — e.g. a HIPAA-compliance question ("I can't confirm...")
   and a request to speak to a named team member ("I'm unable to connect you directly..."). Caught
   by testing adversarial phrasings rather than only the system prompt's primary wording. Fixed
   by broadening the marker list (see "Escalation / contact-capture logging" above). Under-
   detection here is the more serious failure mode — a missed marker means a real lead never gets
   logged — so the fix erred toward a wider net over stricter matching.

3. **Escalation detection still missed capability/account requests (Phase 6).** During the
   Phase 6 adversarial pass, two genuine escalation cases went unlogged: a portal password-reset
   request ("I'm unable to reset passwords for the client portal...") and a billing-email update
   request ("I'm unable to assist with updating account details..."). Both are real declines that
   redirect to the human team — exactly the kind of lead this log exists to capture — but neither
   matched `ESCALATION_MARKERS`, because the existing `"unable to provide"` marker only covered
   the informational-refusal phrasing from Phase 4's fix, not the different "I can't perform this
   action" phrasing the model uses for account/capability requests. Caught by deliberately testing
   an account-modification request as its own category, not just KB-knowledge gaps. Fixed by
   broadening `"unable to provide"` to the more general `"unable to"`, which also covers "unable
   to reset," "unable to assist," "unable to connect," etc. Verified the fix catches both
   previously-missed cases and re-checked two in-scope answers (booking, company overview) to
   confirm no new false positives — one candidate broadening, `"reach out to the team"`, was
   rejected specifically because the booking answer's own "if the link isn't working, feel free
   to reach out to the team at [email]" courtesy line would have false-positived on it.

4. **Dead escalation marker due to a case-sensitivity bug (Phase 8).** `log_if_escalation`
   compares against `reply.lower()`, but one entry in `ESCALATION_MARKERS`, `"I don't have"`,
   kept its capital I — so `marker in lowered` could never match, since `lowered` is always
   fully lowercase. That marker had been silently dead since Phase 6; every reply it was meant
   to catch instead fell through to whatever other marker happened to also match (or, in some
   cases, to no marker at all). Caught immediately by the Phase 8 test suite: a parametrized test
   asserting each marker in `ESCALATION_MARKERS` individually triggers a log line failed for
   exactly this one. Fixed by lowercasing it to `"i don't have"`. This is the clearest concrete
   example so far of the automated suite earning its keep over manual/adversarial testing alone —
   a manual curl pass can miss a bug like this indefinitely if some other marker happens to also
   match on the specific test phrasing used, while a per-marker parametrized test can't.

## Automated test suite (Phase 8)

**Decision:** Add `pytest` + `pytest-html` as dev dependencies and a `tests/test_app.py` suite
(26 tests) covering `backend/app.py`'s routes, request shaping, failure handling, and
`log_if_escalation()`, run via FastAPI's `TestClient` (Starlette's test client, re-exported).
Every OpenRouter call is mocked (`httpx.AsyncClient.post`), so the suite runs offline and never
touches the API budget — verified by running it once with the real `OPENROUTER_API_KEY` unset
and confirming all 26 still pass.

**This reverses the earlier "no automated test suite" scope cut** (see plan.md's "Explicitly
cut" list, now updated). That cut was the right call under the original 4-hour budget — a manual
adversarial pass was the higher-leverage use of limited time for an MVP that didn't exist yet.
Revisited once the MVP was stable and had already been through a real adversarial pass (Phase 6):
at that point the marginal cost of a focused test suite is low, and the payoff is concrete — see
the case-sensitivity bug above, found within minutes of the suite existing, that had been latent
since Phase 6's own testing.

**What's covered vs. not:** All of `backend/app.py`'s testable logic (input validation, history
trimming, max-token capping, OpenRouter failure paths, escalation detection) is covered. The
frontend (`frontend/index.html`) is not — no browser-automation tool is available in this
environment, so its coverage remains the manual/logic-review verification from Phase 3 and
Phase 5, not automated tests. Model output quality (grounding, tone, escalation *phrasing*) also
isn't tested here — that's what Phase 6's live adversarial pass covers, and it can't be mocked
without losing its point.

**Report:** `poetry run pytest --html=report.html --self-contained-html` produces a single
portable HTML file at the project root (gitignored — it's a generated artifact, not source).

## Adversarial test pass summary (Phase 6)

Ran 23 requests against the local server across 6 categories: the 6 required brief scenarios,
3 out-of-scope/escalation questions (pricing, fabricated client name, account-modification
request), 3 prompt-injection attempts, 4 edge cases (empty message, oversized message, Spanish,
emoji/gibberish), a 4-turn multi-history conversation, and 2 hostile-tone messages.

Results: no hallucinated pricing, case studies, or claims; no system-prompt leakage under any of
the 3 injection attempts; tone stayed professional and on-brand under both hostile messages
(no mirroring); multi-turn history correctly recalled context from 3 turns back; empty/oversized
input correctly rejected with a clean `422`, no crash; non-English and gibberish input handled
gracefully. One real bug found and fixed — see item 3 above. This pass ran against the local
server only; the live deployment was separately confirmed by spot-checking equivalent requests before final push.

## Claude Code workflow choices: subagents and custom commands

**Subagents:** Not used in this build. Most phases were genuinely sequential and dependent
on each other (system prompt informs frontend contract, backend must work before adversarial
testing, etc.) — plan.md flagged two phases (3 and 5) as subagent candidates, but given the
4-hour window and that the "independent" work in each case was still fast enough to do
directly, spinning up parallel subagents would have added coordination overhead without a
clear time win at this scale. Subagents are the right call when independent tasks are each
substantial enough that parallelizing saves real wall-clock time — worth revisiting if this
project grew (e.g., building out a full test suite alongside a second feature).

**Custom commands:** Not used. This was a single, one-off 4-hour build with no repeated
workflows — custom commands pay off on tasks done more than once (a recurring deploy-check,
a recurring test sweep, a recurring style-review). If this became an ongoing project, the
adversarial test pass from Phase 6 is the clearest candidate — it was run twice, manually
re-specified both times, and would be a natural first custom command
(e.g. `/adversarial-test`) to save re-typing the full test list on every future change to
the system prompt or KB.