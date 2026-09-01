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

- Direct async request → OpenRouter call → streamed response (SSE), no queue.
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

- [ ] Model choice for the chatbot itself (cost/quality tradeoff) — decide and log
      reasoning here once picked.
- [ ] Whether to add Postgres for lead capture in v1, or keep it to logging only.
- [ ] Two or three specific real examples of Claude Code getting something wrong
      during the actual build, and how you caught/fixed it (needed for Code Deep
      Dive section — capture these live as they happen, don't reconstruct later).
]()