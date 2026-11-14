"""OpenAI-compatible chat client for the runtime extraction LLM (Arvan AIaaS).

Bounded by design: explicit timeout, one endpoint, no retries here (the caller
decides retry policy), and full usage/telemetry returned for cost logging.
Credentials come from the environment; never logged or included in prompts.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import httpx


class LLMError(RuntimeError):
    """Raised for transport, API or unusable-output failures."""


@dataclass
class LLMResponse:
    content: str
    model: str
    finish_reason: str | None
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    raw: dict = field(repr=False, default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def parse_json_loose(content: str) -> dict:
    """Parse a JSON object from model output, tolerating markdown fences."""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("model output is not a JSON object")
    return data


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = (base_url or os.getenv("AIaaS_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("AIaaS_API_KEY", "")
        self.model = model or os.getenv("AIaaS_MODEL", "")
        self.timeout = timeout
        if not self.base_url or not self.api_key or not self.model:
            raise LLMError(
                "LLMClient requires AIaaS_BASE_URL, AIaaS_API_KEY and AIaaS_MODEL "
                "either as arguments or in the environment"
            )
        headers = {"Authorization": f"apikey {self.api_key}"}
        self._client = httpx.Client(
            base_url=self.base_url, headers=headers, timeout=timeout, transport=transport
        )

    def chat(self, messages: list[dict], max_tokens: int = 8000, temperature: float = 0.0) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        if response.status_code != 200:
            raise LLMError(f"LLM API returned HTTP {response.status_code}")
        data = response.json()

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            usage = data.get("usage", {})
            details = usage.get("completion_tokens_details", {}) or {}
            return LLMResponse(
                content=content,
                model=data.get("model", self.model),
                finish_reason=choice.get("finish_reason"),
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                reasoning_tokens=int(details.get("reasoning_tokens", 0)),
                raw=data,
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"unexpected LLM response shape: {exc}") from exc

    def extract_rows(self, messages: list[dict], max_tokens: int = 8000) -> tuple[list[dict], LLMResponse]:
        """Send extraction messages and return parsed row dicts plus telemetry."""
        llm_response = self.chat(messages, max_tokens=max_tokens)
        if llm_response.finish_reason == "length":
            raise LLMError("LLM hit the token limit before completing extraction")
        data = parse_json_loose(llm_response.content)
        rows = data.get("rows")
        if not isinstance(rows, list):
            raise LLMError("model output missing 'rows' list")
        return rows, llm_response

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
