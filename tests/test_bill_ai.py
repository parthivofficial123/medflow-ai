import base64
import io
import json
import socket
import urllib.error
from types import SimpleNamespace

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


@pytest.fixture(autouse=True)
def fake_time(monkeypatch):
    """A clock that only moves when bill_ai waits, so retry tests take no real time."""
    clock = SimpleNamespace(now=1000.0, sleeps=[])

    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds
    monkeypatch.setattr(bill_ai, "sleep", sleep)
    monkeypatch.setattr(bill_ai, "clock", lambda: clock.now)
    return clock


def is_timeout(error):
    return isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)


@pytest.fixture
def gemini(monkeypatch, fake_time):
    """Replace urlopen and record each (request, timeout). Each call gets the next reply in
    order (the last one repeats); an exception is raised, and a timeout uses up its time."""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    requests = []

    def set_replies(*replies):
        def urlopen(request, timeout):
            requests.append((request, timeout))
            reply = replies[min(len(requests), len(replies)) - 1]
            if isinstance(reply, Exception):
                if is_timeout(reply):
                    fake_time.now += timeout
                raise reply
            return FakeResponse(json.dumps(reply).encode())
        monkeypatch.setattr(bill_ai.urllib.request, "urlopen", urlopen)
        return requests

    return set_replies


def http_error(code, retry_delay=None, retry_after=None):
    error = {"code": code, "status": "X", "message": "m"}
    if retry_delay:
        error["details"] = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}]
    headers = {"Retry-After": retry_after} if retry_after else {}
    body = io.BytesIO(json.dumps({"error": error}).encode())
    return urllib.error.HTTPError("https://gemini.invalid/", code, "error", headers, body)


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
    assert request.full_url == ("https://generativelanguage.googleapis.com/v1beta/models/"
                                f"{bill_ai.DEFAULT_MODEL}:generateContent")
    assert timeout == bill_ai.ATTEMPT_TIMEOUT_SECONDS


def test_the_default_model_is_the_light_one():
    assert bill_ai.DEFAULT_MODEL == "gemini-3.5-flash-lite"


def test_gemini_model_setting_chooses_the_model(gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    requests = gemini(gemini_reply())
    bill_ai.call_model(PDF, "application/pdf")
    assert "/models/gemini-3.8-flash:generateContent" in requests[0][0].full_url


@pytest.mark.parametrize("name", ["../tunedModels/x", "gemini flash", "gemini-3.5-flash-lite?alt=sse", "Gemini"])
def test_a_malformed_model_setting_is_refused_before_any_request(gemini, monkeypatch, name):
    monkeypatch.setenv("GEMINI_MODEL", name)
    requests = gemini(gemini_reply())
    with pytest.raises(bill_ai.AIError, match="GEMINI_MODEL") as e:
        bill_ai.call_model(PDF, "application/pdf")
    assert e.value.status == 503 and requests == []


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


@pytest.mark.parametrize("error, status, message, attempts", [
    (http_error(429), 429, "free AI limit", 1),
    (http_error(400), 502, "rejected", 1),
    (http_error(401), 503, "API key", 1),
    (http_error(403), 503, "API key", 1),
    (http_error(404), 502, "rejected", 1),
    (urllib.error.URLError("no route"), 502, "couldn't reach", 1),
    (http_error(500), 502, "having problems", 3),
    (http_error(503), 502, "having problems", 3),
    (socket.timeout("timed out"), 504, "didn't respond in time", 2),
    (TimeoutError("timed out"), 504, "didn't respond in time", 2),
    (urllib.error.URLError(socket.timeout("timed out")), 504, "didn't respond in time", 2),
])
def test_api_failures_become_plain_messages(gemini, error, status, message, attempts):
    requests = gemini(error)
    with pytest.raises(bill_ai.AIError) as e:
        bill_ai.call_model(PDF, "application/pdf")
    assert e.value.status == status
    assert message in e.value.message
    assert FAKE_KEY not in e.value.message
    assert len(requests) == attempts


# Retries: only for errors that are usually brief (busy, overloaded, timed out), a few
# times, with growing waits, and never past one overall time limit.

def test_success_needs_one_request_and_no_waiting(gemini, fake_time):
    requests = gemini(gemini_reply())
    assert json.loads(bill_ai.call_model(PDF, "application/pdf")) == ANSWER
    assert len(requests) == 1 and fake_time.sleeps == []


@pytest.mark.parametrize("code", [500, 502, 503, 504])
def test_a_busy_service_is_retried_and_can_then_succeed(gemini, fake_time, code):
    requests = gemini(http_error(code), gemini_reply())
    assert json.loads(bill_ai.call_model(PDF, "application/pdf")) == ANSWER
    assert len(requests) == 2
    (wait,) = fake_time.sleeps
    assert bill_ai.BACKOFF_SECONDS <= wait <= bill_ai.BACKOFF_SECONDS + 1


def test_retry_waits_grow_and_attempts_are_capped(gemini, fake_time):
    requests = gemini(http_error(503))
    with pytest.raises(bill_ai.AIError, match="having problems"):
        bill_ai.call_model(PDF, "application/pdf")
    assert len(requests) == bill_ai.MAX_ATTEMPTS
    first, second = fake_time.sleeps
    assert second > first


def test_a_timeout_is_retried_within_the_overall_limit(gemini, fake_time):
    requests = gemini(TimeoutError("timed out"), gemini_reply())
    assert json.loads(bill_ai.call_model(PDF, "application/pdf")) == ANSWER
    (_, first), (_, second) = requests
    assert first == bill_ai.ATTEMPT_TIMEOUT_SECONDS
    # The second attempt only gets what is left of the overall limit.
    assert second <= bill_ai.TOTAL_SECONDS - first - fake_time.sleeps[0]


def test_repeated_timeouts_never_run_past_the_overall_limit(gemini, fake_time):
    start = fake_time.now
    requests = gemini(TimeoutError("timed out"))
    with pytest.raises(bill_ai.AIError, match="didn't respond in time") as e:
        bill_ai.call_model(PDF, "application/pdf")
    assert e.value.status == 504
    assert fake_time.now - start <= bill_ai.TOTAL_SECONDS
    assert len(requests) <= bill_ai.MAX_ATTEMPTS


@pytest.mark.parametrize("error", [http_error(429, retry_delay="3s"), http_error(429, retry_after="3")])
def test_a_short_rate_limit_is_retried_after_the_wait_google_asks_for(gemini, fake_time, error):
    requests = gemini(error, gemini_reply())
    assert json.loads(bill_ai.call_model(PDF, "application/pdf")) == ANSWER
    assert len(requests) == 2 and fake_time.sleeps == [3.0]


@pytest.mark.parametrize("error", [http_error(429), http_error(429, retry_delay="45s"),
                                   http_error(429, retry_delay="soon")])
def test_a_long_or_unknown_rate_limit_is_not_retried(gemini, fake_time, error):
    requests = gemini(error)
    with pytest.raises(bill_ai.AIError, match="free AI limit"):
        bill_ai.call_model(PDF, "application/pdf")
    assert len(requests) == 1 and fake_time.sleeps == []


def test_a_completed_but_unusable_reply_is_not_retried(gemini):
    requests = gemini(gemini_reply(finish="SAFETY"), gemini_reply())
    with pytest.raises(bill_ai.AIError, match="declined"):
        bill_ai.call_model(PDF, "application/pdf")
    assert len(requests) == 1


def test_retries_are_logged_without_the_key_or_bill(gemini, caplog):
    gemini(http_error(503), gemini_reply())
    bill_ai.call_model(PDF, "application/pdf")
    assert "503" in caplog.text and "retrying" in caplog.text
    assert FAKE_KEY not in caplog.text and "fictional test bill" not in caplog.text


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
    calls = []

    def urlopen(request, timeout):
        calls.append(request)
        return FakeResponse(b"<html>gateway error</html>")
    monkeypatch.setattr(bill_ai.urllib.request, "urlopen", urlopen)
    with pytest.raises(bill_ai.AIError, match="unexpected reply"):
        bill_ai.call_model(PDF, "application/pdf")
    assert len(calls) == 1


def test_model_text_that_is_not_json_is_an_error(gemini):
    gemini(gemini_reply(parts=[{"text": "Here is the bill: {not json"}]))
    with pytest.raises(bill_ai.AIError, match="couldn't read the AI's answer"):
        bill_ai.extract(PDF, "application/pdf")


def test_extract_returns_the_answer_as_data(gemini):
    gemini(gemini_reply())
    assert bill_ai.extract(PDF, "application/pdf") == ANSWER


def test_failures_are_logged_without_the_key(gemini, caplog):
    gemini(http_error(429))
    with pytest.raises(bill_ai.AIError):
        bill_ai.call_model(PDF, "application/pdf")
    assert "429" in caplog.text
    assert FAKE_KEY not in caplog.text


def test_a_zero_wait_from_google_still_backs_off(gemini, fake_time):
    gemini(http_error(429, retry_after="0"), gemini_reply())
    bill_ai.call_model(PDF, "application/pdf")
    assert fake_time.sleeps == [bill_ai.BACKOFF_SECONDS]
