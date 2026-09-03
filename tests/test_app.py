"""
Tests for backend/app.py, run via Starlette's TestClient (re-exported by FastAPI).

Every OpenRouter call is mocked (httpx.AsyncClient.post) — no test hits the real API, so the
suite runs offline and costs nothing against the $5 budget. See DECISIONS.md for why this phase
exists (originally cut from the build, revisited once the MVP was stable).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend.app import (
    ESCALATION_MARKERS,
    MAX_HISTORY_MESSAGES,
    MAX_MESSAGE_LENGTH,
    MAX_RESPONSE_TOKENS,
    OPENROUTER_URL,
    app,
    log_if_escalation,
)
from backend.prompts import SYSTEM_PROMPT

client = TestClient(app)


class FakeResponse:
    """Minimal stand-in for httpx.Response: sync raise_for_status()/json(), like the real thing."""

    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", OPENROUTER_URL)
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._json_data


def _completion(content="Mocked response content."):
    return FakeResponse({"choices": [{"message": {"content": content}}]})


@pytest.fixture(autouse=True)
def ensure_api_key(monkeypatch):
    # Most tests need a "configured" key so they exercise the OpenRouter call path, not the
    # early config-error return. The one test that wants the unconfigured path overrides this.
    monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", "test-key")


def _mock_post():
    return patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)


# --- Route-level tests -------------------------------------------------------------------


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_index_serves_frontend_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    on_disk = (Path(__file__).resolve().parent.parent / "frontend" / "index.html").read_text()
    assert resp.text == on_disk


# --- POST /api/chat: input validation ----------------------------------------------------


def test_chat_missing_message_field_rejected():
    with _mock_post() as mock_post:
        resp = client.post("/api/chat", json={})
    assert resp.status_code == 422
    mock_post.assert_not_called()


def test_chat_empty_message_rejected():
    with _mock_post() as mock_post:
        resp = client.post("/api/chat", json={"message": ""})
    assert resp.status_code == 422
    mock_post.assert_not_called()


def test_chat_oversized_message_rejected():
    with _mock_post() as mock_post:
        resp = client.post("/api/chat", json={"message": "a" * (MAX_MESSAGE_LENGTH + 1)})
    assert resp.status_code == 422
    mock_post.assert_not_called()


def test_chat_message_at_max_length_accepted():
    with _mock_post() as mock_post:
        mock_post.return_value = _completion("ok")
        resp = client.post("/api/chat", json={"message": "a" * MAX_MESSAGE_LENGTH})
    assert resp.status_code == 200
    assert resp.json() == {"response": "ok"}


def test_chat_missing_history_defaults_to_empty():
    with _mock_post() as mock_post:
        mock_post.return_value = _completion("hi there")
        resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    sent_messages = mock_post.call_args.kwargs["json"]["messages"]
    # Only the system message and the new user message — no history entries.
    assert len(sent_messages) == 2


# --- POST /api/chat: request shaping ------------------------------------------------------


def test_chat_system_prompt_always_first():
    with _mock_post() as mock_post:
        mock_post.return_value = _completion()
        client.post("/api/chat", json={"message": "hi"})
    sent = mock_post.call_args.kwargs["json"]["messages"]
    assert sent[0] == {"role": "system", "content": SYSTEM_PROMPT}


def test_chat_history_forwarded_in_order():
    history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    with _mock_post() as mock_post:
        mock_post.return_value = _completion()
        client.post("/api/chat", json={"message": "third", "history": history})
    sent = mock_post.call_args.kwargs["json"]["messages"]
    assert [m["content"] for m in sent] == [SYSTEM_PROMPT, "first", "second", "third"]


def test_chat_history_trimmed_to_last_n():
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
        for i in range(14)
    ]
    with _mock_post() as mock_post:
        mock_post.return_value = _completion()
        client.post("/api/chat", json={"message": "new message", "history": history})
    sent = mock_post.call_args.kwargs["json"]["messages"]
    # system + last MAX_HISTORY_MESSAGES history entries + the new user message
    assert len(sent) == 1 + MAX_HISTORY_MESSAGES + 1
    history_in_request = sent[1:-1]
    expected = history[-MAX_HISTORY_MESSAGES:]
    assert [m["content"] for m in history_in_request] == [h["content"] for h in expected]


def test_chat_max_tokens_always_set():
    with _mock_post() as mock_post:
        mock_post.return_value = _completion()
        client.post("/api/chat", json={"message": "hi"})
    assert mock_post.call_args.kwargs["json"]["max_tokens"] == MAX_RESPONSE_TOKENS


# --- POST /api/chat: happy path -----------------------------------------------------------


def test_chat_happy_path_returns_model_content():
    with _mock_post() as mock_post:
        mock_post.return_value = _completion("Cadre AI offers AI Strategy, AI Agents, and more.")
        resp = client.post("/api/chat", json={"message": "What does Cadre AI do?"})
    assert resp.status_code == 200
    assert resp.json() == {"response": "Cadre AI offers AI Strategy, AI Agents, and more."}


# --- POST /api/chat: failure handling ------------------------------------------------------


def test_chat_timeout_returns_graceful_message():
    with _mock_post() as mock_post:
        mock_post.side_effect = httpx.TimeoutException("timed out")
        resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 200
    assert "trouble reaching" in resp.json()["response"]


def test_chat_http_status_error_returns_graceful_message():
    request = httpx.Request("POST", OPENROUTER_URL)
    response = httpx.Response(401, request=request)
    with _mock_post() as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError(
            "unauthorized", request=request, response=response
        )
        resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 200
    assert "trouble reaching" in resp.json()["response"]


def test_chat_malformed_response_returns_graceful_message():
    with _mock_post() as mock_post:
        mock_post.return_value = FakeResponse({"unexpected": "shape"})  # no "choices" key
        resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 200
    assert "trouble reaching" in resp.json()["response"]


def test_chat_missing_api_key_returns_graceful_message(monkeypatch):
    monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", None)
    with _mock_post() as mock_post:
        resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 200
    assert "isn't configured correctly" in resp.json()["response"]
    mock_post.assert_not_called()


# --- log_if_escalation(): pure-function unit tests --------------------------------------


@pytest.mark.parametrize("marker", ESCALATION_MARKERS)
def test_log_if_escalation_detects_each_marker(capsys, marker):
    reply = f"Some preamble text. {marker} more context here."
    log_if_escalation("What is your pricing?", reply)
    captured = capsys.readouterr()
    assert captured.out.startswith("ESCALATION: user asked 'What is your pricing?' | response:")


def test_log_if_escalation_no_markers_no_output(capsys):
    log_if_escalation(
        "What does Cadre AI do?",
        "Cadre AI is a consultancy that helps businesses adopt AI strategically.",
    )
    captured = capsys.readouterr()
    assert captured.out == ""


def test_log_if_escalation_flattens_newlines(capsys):
    log_if_escalation("multi\nline\nmessage", "I don't have that information.\nPlease reach out.")
    captured = capsys.readouterr()
    # Exactly one newline in the output: the trailing one print() adds.
    assert captured.out.count("\n") == 1


def test_log_if_escalation_exact_message_and_reply_content(capsys):
    log_if_escalation("hello", "I don't have that information about pricing.")
    captured = capsys.readouterr()
    assert "user asked 'hello'" in captured.out
    assert "response: 'I don't have that information about pricing.'" in captured.out
