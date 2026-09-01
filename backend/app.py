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

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    response: str


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

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in payload.history]
    messages.append({"role": "user", "content": payload.message})

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={"model": MODEL, "messages": messages},
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

    return ChatResponse(response=reply)
