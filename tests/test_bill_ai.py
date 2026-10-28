import base64
import io
import json
import socket
import urllib.error

import pytest

from medflow import bill_ai

PDF = b"%PDF-1.4\n% fictional test bill\n"
FAKE_KEY = "test-key-not-real"
ANSWER = {"provider": "Lakeside Imaging (fictional)", "bill_date": "", "total": "", "items": []}


def gemini_reply(answer=ANSWER, finish="STOP", parts=None):
    parts = parts if parts is not None else [{"text": json.dumps(answer)}]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def gemini(monkeypatch):
    """Replace urlopen; record each request; reply with the given payload or raise the given error."""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    requests = []

    def set_reply(reply):
        def urlopen(request, timeout):
            requests.append((request, timeout))
            if isinstance(reply, Exception):
                raise reply
            return FakeResponse(json.dumps(reply).encode())
        monkeypatch.setattr(bill_ai.urllib.request, "urlopen", urlopen)
        return requests

    return set_reply


def http_error(code):
    body = io.BytesIO(json.dumps({"error": {"code": code, "status": "X", "message": "m"}}).encode())
    return urllib.error.HTTPError(bill_ai.API_URL, code, "error", {}, body)


def test_no_key_means_not_configured(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(bill_ai.AIError, match="isn't configured") as e:
        bill_ai.call_model(PDF, "application/pdf")
    assert e.value.status == 503


def test_request_sends_file_prompt_and_schema(gemini):
    requests = gemini(gemini_reply())
    bill_ai.call_model(PDF, "application/pdf")
    (request, timeout), = requests
    body = json.loads(request.data)
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"inline_data": {"mime_type": "application/pdf",
                                        "data": base64.b64encode(PDF).decode()}}
    assert parts[1] == {"text": bill_ai.PROMPT}
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == bill_ai.ANSWER_SCHEMA
    assert request.get_method() == "POST"
    assert bill_ai.MODEL in request.full_url
    assert timeout == bill_ai.TIMEOUT_SECONDS


def test_key_goes_in_a_header_never_the_url(gemini):
    requests = gemini(gemini_reply())
    bill_ai.call_model(PDF, "application/pdf")
    request = requests[0][0]
    assert request.get_header("X-goog-api-key") == FAKE_KEY
    assert FAKE_KEY not in request.full_url


def test_reply_text_is_returned(gemini):
    gemini(gemini_reply())
    assert json.loads(bill_ai.call_model(PDF, "application/pdf")) == ANSWER


def test_thought_parts_are_skipped(gemini):
    gemini(gemini_reply(parts=[{"text": "thinking...", "thought": True}, {"text": json.dumps(ANSWER)}]))
    assert json.loads(bill_ai.call_model(PDF, "application/pdf")) == ANSWER


@pytest.mark.parametrize("error, status, message", [
    (http_error(429), 429, "free AI limit"),
    (http_error(400), 502, "rejected"),
    (http_error(401), 503, "API key"),
    (http_error(403), 503, "API key"),
    (http_error(404), 502, "rejected"),
    (http_error(500), 502, "having problems"),
    (http_error(503), 502, "having problems"),
    (socket.timeout("timed out"), 504, "didn't respond in time"),
    (TimeoutError("timed out"), 504, "didn't respond in time"),
    (urllib.error.URLError(socket.timeout("timed out")), 504, "didn't respond in time"),
    (urllib.error.URLError("no route"), 502, "couldn't reach"),
])
def test_api_failures_become_plain_messages(gemini, error, status, message):
    gemini(error)
    with pytest.raises(bill_ai.AIError) as e:
        bill_ai.call_model(PDF, "application/pdf")
    assert e.value.status == status
    assert message in e.value.message
    assert FAKE_KEY not in e.value.message


@pytest.mark.parametrize("reply, message", [
    ({"promptFeedback": {"blockReason": "SAFETY"}}, "declined"),
    ({"candidates": []}, "declined"),
    (gemini_reply(finish="SAFETY"), "declined"),
    (gemini_reply(finish="MAX_TOKENS"), "too long"),
    (gemini_reply(parts=[]), "declined"),
    ({"unexpected": True}, "declined"),
    ([], "declined"),
])
def test_unusable_replies_become_plain_messages(gemini, reply, message):
    gemini(reply)
    with pytest.raises(bill_ai.AIError, match=message):
        bill_ai.call_model(PDF, "application/pdf")


def test_reply_that_is_not_json_is_an_error(gemini, monkeypatch):
    def urlopen(request, timeout):
        return FakeResponse(b"<html>gateway error</html>")
    monkeypatch.setattr(bill_ai.urllib.request, "urlopen", urlopen)
    with pytest.raises(bill_ai.AIError, match="unexpected reply"):
        bill_ai.call_model(PDF, "application/pdf")


def test_failures_are_logged_without_the_key(gemini, caplog):
    gemini(http_error(429))
    with pytest.raises(bill_ai.AIError):
        bill_ai.call_model(PDF, "application/pdf")
    assert "429" in caplog.text
    assert FAKE_KEY not in caplog.text
