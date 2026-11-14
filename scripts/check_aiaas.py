"""Bounded Arvan AIaaS connectivity check.

Milestone 2, item 2: verify endpoint, authentication and available models.
This script only performs a GET /models request (control plane, no inference,
no token cost) unless --chat-test is passed, in which case it sends one
minimal chat completion with a tiny max_tokens budget.
"""

from __future__ import annotations

import argparse
import sys

import httpx
from dotenv import load_dotenv
import os


def get_credentials() -> tuple[str, str]:
    load_dotenv()
    base_url = os.getenv("AIaaS_BASE_URL", "").rstrip("/")
    api_key = os.getenv("AIaaS_API_KEY", "")
    if not base_url or not api_key:
        print("ERROR: AIaaS_BASE_URL and AIaaS_API_KEY must be set in .env")
        sys.exit(2)
    return base_url, api_key


def check_models(base_url: str, api_key: str) -> list[str]:
    response = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"apikey {api_key}"},
        timeout=15.0,
    )
    print(f"GET {base_url}/models -> HTTP {response.status_code}")
    response.raise_for_status()
    payload = response.json()
    # OpenAI-compatible shape: {"data": [{"id": ...}, ...]}
    models = [item.get("id") for item in payload.get("data", [])]
    return [m for m in models if m]


def chat_test(base_url: str, api_key: str, model: str) -> None:
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"apikey {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
            "max_tokens": 10,
            "temperature": 0,
        },
        timeout=60.0,
    )
    print(f"POST {base_url}/chat/completions -> HTTP {response.status_code}")
    print(response.text[:2000])


def main() -> None:
    parser = argparse.ArgumentParser(description="Arvan AIaaS connectivity check")
    parser.add_argument("--chat-test", action="store_true", help="also send one minimal chat completion (billable, ~10 tokens)")
    parser.add_argument("--model", default="", help="model to use with --chat-test")
    args = parser.parse_args()

    base_url, api_key = get_credentials()

    models = check_models(base_url, api_key)
    print(f"Available models ({len(models)}):")
    for m in models:
        print(f"  - {m}")

    if args.chat_test:
        model = args.model or os.getenv("AIaaS_MODEL", "")
        if not model:
            print("ERROR: no model specified (use --model or set AIaaS_MODEL)")
            sys.exit(2)
        chat_test(base_url, api_key, model)


if __name__ == "__main__":
    main()
