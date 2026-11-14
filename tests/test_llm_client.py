"""Tests for the OpenAI-compatible LLM client, fully mocked (no live calls)."""

import json
from pathlib import Path

import httpx
import pytest

from extractors.llm import LLMClient, LLMError

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arvan_cloud_server"


def make_client(handler) -> LLMClient:
    return LLMClient(
        base_url="https://mock.local/v1",
        api_key="test-key",
        model="Test-Model",
        transport=httpx.MockTransport(handler),
    )


def openai_envelope(content: str, finish_reason: str = "stop", completion: int = 42) -> dict:
    return {
        "choices": [{"finish_reason": finish_reason, "index": 0, "message": {"role": "assistant", "content": content}}],
        "model": "Test-Model",
        "usage": {
            "prompt_tokens": 13,
            "completion_tokens": completion,
            "completion_tokens_details": {"reasoning_tokens": 7},
        },
    }


def test_extract_rows_parses_mocked_response_and_usage():
    rows = json.loads((FIXTURES / "llm_rows_basic.json").read_text(encoding="utf-8"))["rows"]
    content = json.dumps({"rows": rows}, ensure_ascii=False)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "Test-Model"
        assert body["temperature"] == 0.0
        assert body["max_tokens"] == 8000
        # credentials must go to the authorization header, never the payload
        assert "test-key" not in request.content.decode()
        assert request.headers["Authorization"].startswith("apikey ")
        return httpx.Response(200, json=openai_envelope(content))

    with make_client(handler) as client:
        parsed, telemetry = client.extract_rows([{"role": "user", "content": "x"}])
    assert parsed == rows
    assert telemetry.prompt_tokens == 13
    assert telemetry.completion_tokens == 42
    assert telemetry.reasoning_tokens == 7
    assert telemetry.finish_reason == "stop"


def test_extract_rows_tolerates_markdown_fences():
    rows = json.loads((FIXTURES / "llm_rows_basic.json").read_text(encoding="utf-8"))["rows"]
    fenced = "```json\n" + json.dumps({"rows": rows}, ensure_ascii=False) + "\n```"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openai_envelope(fenced))

    with make_client(handler) as client:
        parsed, _ = client.extract_rows([{"role": "user", "content": "x"}])
    assert len(parsed) == 8


def test_token_limit_failure_is_visible():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openai_envelope("partial", finish_reason="length"))

    with make_client(handler) as client:
        with pytest.raises(LLMError, match="token limit"):
            client.extract_rows([{"role": "user", "content": "x"}])


def test_malformed_json_is_visible():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=openai_envelope("this is not json"))

    with make_client(handler) as client:
        with pytest.raises(LLMError, match="not valid JSON"):
            client.extract_rows([{"role": "user", "content": "x"}])


def test_http_error_is_visible():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with make_client(handler) as client:
        with pytest.raises(LLMError, match="HTTP 500"):
            client.extract_rows([{"role": "user", "content": "x"}])


def test_client_requires_configuration(monkeypatch):
    monkeypatch.delenv("AIaaS_BASE_URL", raising=False)
    monkeypatch.delenv("AIaaS_API_KEY", raising=False)
    monkeypatch.delenv("AIaaS_MODEL", raising=False)
    with pytest.raises(LLMError, match="AIaaS_BASE_URL"):
        LLMClient()
