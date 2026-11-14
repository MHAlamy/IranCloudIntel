"""Inspect Arvan's cloud-server pricing page structure.

Milestone 2, first increment: determine how pricing content is delivered
(static HTML, embedded JSON, or JavaScript-rendered) before designing
collection and fixtures. Saves raw evidence under evidence/ (gitignored).
Free operation: plain HTTP only, no LLM calls.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Windows consoles default to legacy codepages; force UTF-8 output.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

TARGET_URL = "https://www.arvancloud.ir/fa/pricing/cloud-server"
EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "evidence" / "arvan" / "cloud-server"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Signals for how the page delivers content
EMBEDDED_JSON_MARKERS = [
    "__NEXT_DATA__",
    "__NUXT__",
    "application/ld+json",
    "application/json",
    "window.__",
]

PRICING_KEYWORDS = [
    "eco-small",
    "standard",
    "premium",
    "vCPU",
    "vcpu",
    "تومان",
    "ریال",
    "پردازنده",
    "حافظه",
]


def fetch(url: str) -> httpx.Response:
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "fa,en;q=0.8"},
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response


def save_evidence(content: bytes, suffix: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()[:12]
    path = EVIDENCE_DIR / f"{stamp}_{digest}{suffix}"
    path.write_bytes(content)
    return path


def main() -> None:
    print(f"Fetching {TARGET_URL}")
    response = fetch(TARGET_URL)
    html = response.text
    print(f"HTTP {response.status_code}, final URL: {response.url}")
    print(f"HTML length: {len(html):,} characters")

    raw_path = save_evidence(response.content, "_raw.html")
    print(f"Raw evidence saved: {raw_path}")

    print("\n-- Embedded JSON markers --")
    for marker in EMBEDDED_JSON_MARKERS:
        count = html.count(marker)
        if count:
            print(f"  {marker}: {count} occurrence(s)")

    print("\n-- Pricing keywords in raw HTML --")
    for keyword in PRICING_KEYWORDS:
        count = html.count(keyword)
        print(f"  {keyword}: {count}")

    # Extract inline JSON script blocks and inspect their top-level keys
    print("\n-- Inline JSON/script blocks --")
    script_blocks = re.findall(
        r"<script[^>]*type=[\"']application/(?:ld\+)?json[\"'][^>]*>(.*?)</script>",
        html,
        re.DOTALL,
    )
    for i, block in enumerate(script_blocks[:10]):
        try:
            data = json.loads(block)
            keys = list(data.keys()) if isinstance(data, dict) else f"[{type(data).__name__}]"
            print(f"  block {i}: JSON ok, keys={keys if isinstance(keys, str) else keys[:12]}")
        except json.JSONDecodeError:
            print(f"  block {i}: not valid JSON (len={len(block)})")

    # Heuristic: does raw HTML already contain recognizable plan identifiers?
    plan_hits = re.findall(r"eco-\w+|general-\w+|standard-\w+|premium-\w+", html)
    print(f"\n-- Plan-like tokens found in raw HTML: {sorted(set(plan_hits))[:20]}")

    # Framework hints
    frameworks = []
    if "_next" in html or "__NEXT_DATA__" in html:
        frameworks.append("Next.js")
    if "__NUXT__" in html or "/_nuxt/" in html:
        frameworks.append("Nuxt")
    if "ng-state" in html or "angular" in html.lower():
        frameworks.append("Angular")
    if 'id="root"' in html or 'id="app"' in html:
        frameworks.append("SPA root mount (React/Vue/Angular likely)")
    print(f"Framework hints: {frameworks or 'none detected'}")

    print("\nDone.")


if __name__ == "__main__":
    sys.exit(main())
