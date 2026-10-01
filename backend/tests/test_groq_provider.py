"""Groq through the shared provider contract, using mocked HTTP only (no real key needed)."""

import json
import logging

import httpx
import pytest
from pydantic import SecretStr

from app import providers
from app.config import settings
from app.providers import LocalProvider, ModelFailure, provider, strict_schema
from app.schemas import Draft, Extracted

KEY = "gsk_fixture_SECRET_value_123"
URL = "https://api.groq.com/openai/v1"


@pytest.fixture
def groq(monkeypatch):
    s = settings()
    for name, value in {
        "model_provider": "groq",
        "model_base_url": URL,
        "model_name": "openai/gpt-oss-120b",
        "groq_api_key": SecretStr(KEY),
        "model_reasoning_effort": "medium",
    }.items():
        monkeypatch.setattr(s, name, value)
    sleeps = []
    monkeypatch.setattr(providers.time, "sleep", sleeps.append)
    return sleeps


def respond(monkeypatch, *responses):
    """Each call pops the next (status, body | exception, headers)."""
    calls = []
    queue = list(responses)

    def post(self, url, **kwargs):
        calls.append({"url": url, **kwargs})
        status, body, headers = queue.pop(0)
        if isinstance(body, Exception):
            raise body
        content = body if isinstance(body, dict) else {"choices": [{"message": {"content": body}}]}
        return httpx.Response(
            status, json=content, headers=headers or {}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    return calls


def ok(content, usage=None):
    return (200, {"choices": [{"message": {"content": content}}], "usage": usage or {}}, None)


def failure(category_text, call):
    with pytest.raises(ModelFailure) as error:
        call()
    assert str(error.value) == category_text
    assert KEY not in str(error.value) and error.value.__cause__ is None
    return error


def test_groq_request_is_strict_authenticated_and_tool_free(groq, monkeypatch, caplog):
    calls = respond(
        monkeypatch,
        ok(
            '{"candidates":[{"requirement_id":"tax","field":"tax_id","value":"T-1","quote":"tax T-1"}]}',
            {"prompt_tokens": 120, "completion_tokens": 40},
        ),
    )
    with caplog.at_level(logging.INFO, logger="app.providers"):
        result = LocalProvider().structured("Extract", {"document": "tax T-1"}, Extracted)
    assert result.candidates[0].value == "T-1"
    [call] = calls
    body = call["json"]
    assert call["url"] == URL + "/chat/completions"
    assert call["headers"] == {"Authorization": "Bearer " + KEY}
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["reasoning_effort"] == "medium" and body["include_reasoning"] is False
    assert not {"tools", "tool_choice", "max_tokens"} & set(body)
    assert body["response_format"]["json_schema"]["strict"] is True
    metrics = json.loads(caplog.records[-1].getMessage().split(" ", 1)[1])
    assert metrics["outcome"] == "ok" and metrics["prompt_tokens"] == 120
    assert KEY not in caplog.text and "tax T-1" not in caplog.text


def test_strict_transport_schema_is_closed_and_fully_required():
    schema = strict_schema(Extracted.model_json_schema())
    candidate = schema["$defs"]["Candidate"]
    assert schema["required"] == ["candidates"] and schema["additionalProperties"] is False
    assert candidate["required"] == ["requirement_id", "field", "value", "quote"]
    assert candidate["additionalProperties"] is False
    assert "minLength" not in json.dumps(schema) and "default" not in json.dumps(schema)
    assert strict_schema(Draft.model_json_schema())["required"] == ["message"]


def test_application_validation_still_applies_after_transport_relaxation(groq, monkeypatch):
    # minLength is not sent to Groq, but Pydantic still rejects an empty value.
    empty = '{"candidates":[{"requirement_id":"tax","field":"tax_id","value":"","quote":"q"}]}'
    calls = respond(monkeypatch, ok(empty), ok(empty))
    failure(
        "Model returned invalid structured output",
        lambda: LocalProvider().structured("x", {}, Extracted),
    )
    assert len(calls) == 2


def test_missing_key_or_plaintext_endpoint_is_a_config_failure(groq, monkeypatch):
    calls = respond(monkeypatch)
    monkeypatch.setattr(settings(), "groq_api_key", None)
    failure("Model provider is not configured", lambda: LocalProvider().structured("x", {}, Draft))
    monkeypatch.setattr(settings(), "groq_api_key", SecretStr(KEY))
    monkeypatch.setattr(settings(), "model_base_url", "http://api.groq.com/openai/v1")
    failure("Model provider is not configured", lambda: LocalProvider().structured("x", {}, Draft))
    assert not calls


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_credentials_are_not_retried(groq, monkeypatch, status):
    calls = respond(monkeypatch, (status, {"error": {"message": "Invalid API Key"}}, None))
    failure(
        "Model provider rejected its credentials",
        lambda: LocalProvider().structured("x", {}, Draft),
    )
    assert len(calls) == 1 and not groq


def test_rate_limit_retries_once_with_capped_backoff(groq, monkeypatch, caplog):
    limited = (429, {"error": {"message": "rate"}}, {"retry-after": "30"})
    calls = respond(monkeypatch, limited, limited)
    with caplog.at_level(logging.INFO, logger="app.providers"):
        failure(
            "Model provider rate limit reached",
            lambda: LocalProvider().structured("x", {}, Draft),
        )
    assert len(calls) == 2 and groq == [5]
    assert KEY not in caplog.text


def test_server_error_then_success(groq, monkeypatch):
    calls = respond(monkeypatch, (503, {"error": {}}, None), ok('{"message":"Please send tax"}'))
    assert LocalProvider().structured("x", {}, Draft).message == "Please send tax"
    assert len(calls) == 2 and groq == [1]


def test_repeated_server_error_or_timeout_is_unavailable(groq, monkeypatch):
    respond(monkeypatch, (500, {}, None), (502, {}, None))
    failure("Model provider unavailable", lambda: LocalProvider().structured("x", {}, Draft))
    calls = respond(
        monkeypatch,
        (0, httpx.ReadTimeout("slow"), None),
        (0, httpx.ConnectError("down"), None),
    )
    failure("Model provider unavailable", lambda: LocalProvider().structured("x", {}, Draft))
    assert len(calls) == 2


def test_strict_schema_rejection_and_malformed_output(groq, monkeypatch):
    rejected = (400, {"error": {"code": "json_validate_failed"}}, None)
    calls = respond(monkeypatch, rejected, rejected)
    failure(
        "Model returned invalid structured output",
        lambda: LocalProvider().structured("x", {}, Draft),
    )
    assert len(calls) == 2
    respond(monkeypatch, ok("not json"), (200, {"choices": []}, None))
    failure(
        "Model returned invalid structured output",
        lambda: LocalProvider().structured("x", {}, Draft),
    )
    respond(monkeypatch, ok('{"message":"x","approved":true}'), ok('{"message":"x","tool":"sql"}'))
    failure(
        "Model returned invalid structured output",
        lambda: LocalProvider().structured("x", {}, Draft),
    )


def test_groq_is_selected_by_configuration_only(groq):
    assert isinstance(provider(), LocalProvider)
