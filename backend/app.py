import os
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.prompts import SYSTEM_PROMPT

# load_dotenv() walks up from this file's directory to find `.env`, so it finds the
# project-root .env regardless of whether uvicorn is launched from backend/ or the repo root.
# In production (Railway/Render) the var is set directly in the platform env, so this is a
# no-op there — .env is never committed/deployed.
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Locked in per DECISIONS.md: cheapest reliable model for a fixed $5/7-day budget.
MODEL = "openai/gpt-4o-mini"
# Caps output length per request — protects the $5/7-day budget from a runaway or adversarial
# response. SYSTEM_PROMPT already asks for "a few sentences to a short paragraph," so 500 tokens
# is generous headroom for a normal answer while still bounding the worst case.
MAX_RESPONSE_TOKENS = 500
# Caps input length — an unbounded message is both a cost vector (charged per input token) and
# a bad-experience vector (nothing in this support-chat use case needs a multi-page message).
MAX_MESSAGE_LENGTH = 2000
# Caps how much prior conversation gets sent to OpenRouter per request. The frontend keeps the
# full thread for display, but an unbounded `history` re-sent on every turn grows cost linearly
# with conversation length and can eventually exceed the model's context window. 10 messages =
# 5 user/assistant exchanges — enough for this bot's short support-style conversations.
MAX_HISTORY_MESSAGES = 10

# Heuristic markers tied to the escalation wording in prompts.SYSTEM_PROMPT ("say plainly that
# you don't have that information ... Ask for their name and email"). Simple substring check
# instead of a separate classification call, per plan.md Phase 4 — retune if that wording changes.
ESCALATION_MARKERS = ("don't have that information",
                      "name and email",
                      "cannot provide",
                      "can't confirm",
                      "unable to provide",
                      "I don't have",
                      "reaching out to the team")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str


def log_if_escalation(message: str, reply: str) -> None:
    lowered = reply.lower()
    if not any(marker in lowered for marker in ESCALATION_MARKERS):
        return
    # Single-line, prefixed for easy `grep ESCALATION:` in Railway/Render logs — no DB in v1
    # (see CLAUDE.md), so stdout is the lead-capture record for now.
    safe_message = message.replace("\n", " ")
    safe_reply = reply.replace("\n", " ")
    print(f"ESCALATION: user asked '{safe_message}' | response: '{safe_reply}'")


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if not OPENROUTER_API_KEY:
        # Fails loudly in logs but still returns a normal chat-shaped response so the
        # (not-yet-built) frontend never has to special-case a config error.
        print("ERROR: OPENROUTER_API_KEY is not set")
        return ChatResponse(
            response="Sorry, the chat service isn't configured correctly. Please try again later."
        )

    # Keep only the most recent exchanges — see MAX_HISTORY_MESSAGES.
    trimmed_history = payload.history[-MAX_HISTORY_MESSAGES:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in trimmed_history]
    messages.append({"role": "user", "content": payload.message})

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={"model": MODEL, "messages": messages, "max_tokens": MAX_RESPONSE_TOKENS},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
    except (httpx.HTTPStatusError, httpx.RequestError, KeyError, IndexError) as exc:
        # httpx.TimeoutException is a subclass of RequestError, so it's covered here too.
        # KeyError/IndexError guard against an OpenRouter response that doesn't have the
        # expected shape (e.g. an error body instead of a completion).
        # Logged to stdout, not raised — plan.md Phase 5 wants a graceful message here,
        # not a raw 500, and stdout is visible in the platform's logs for the MVP.
        print(f"OpenRouter call failed: {exc!r}")
        return ChatResponse(
            response="Sorry, I'm having trouble reaching the chat service right now. "
            "Please try again in a moment."
        )

    log_if_escalation(payload.message, reply)
    return ChatResponse(response=reply)
