"""Inspect Arvan's cloud-server pricing page with a real browser.

The site sits behind a JavaScript challenge and renders tabs dynamically,
so plain HTTP cannot reach the pricing content. This script uses Playwright
with the system Microsoft Edge (channel="msedge") — Playwright's browser
CDN is geo-blocked, so we use the preinstalled browser instead of downloading
Chromium.

Outputs (all under evidence/, gitignored):
- final rendered HTML
- screenshot
- catalog of JSON API responses the page fetched (passive observation only)

Free operation: no LLM calls, public page only.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from collectors.browser import launch_browser

TARGET_URL = "https://www.arvancloud.ir/fa/pricing/cloud-server"
EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "evidence" / "arvan" / "cloud-server"

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PRICING_SIGNALS = ["eco-small", "standard", "premium", "تومان", "پردازنده", "حافظه"]


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save(content: bytes, suffix: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()[:12]
    path = EVIDENCE_DIR / f"{stamp()}_{digest}{suffix}"
    path.write_bytes(content)
    return path


def main() -> None:
    json_responses: list[dict] = []

    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")

        def on_response(response):
            url = response.url
            ctype = response.headers.get("content-type", "")
            if "json" in ctype and "arvancloud" in url:
                try:
                    body = response.text()
                except Exception:
                    return
                # Ignore trivially small payloads (analytics/beacons)
                if len(body) > 200:
                    json_responses.append({"url": url, "length": len(body), "body": body})

        page.on("response", on_response)

        print(f"Navigating to {TARGET_URL}")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60_000)

        # Wait until real pricing content appears (challenge pages redirect/reload).
        content_seen = False
        for attempt in range(12):  # up to ~60s
            page.wait_for_timeout(5_000)
            html = page.content()
            if any(signal in html for signal in PRICING_SIGNALS):
                content_seen = True
                break
            print(f"  waiting for pricing content... ({(attempt + 1) * 5}s, len={len(html):,})")

        html = page.content()
        print(f"\nFinal URL: {page.url}")
        print(f"Title: {page.title()}")
        print(f"Rendered HTML length: {len(html):,} characters")
        print(f"Pricing content detected: {content_seen}")

        html_path = save(html.encode("utf-8"), "_rendered.html")
        print(f"Rendered HTML saved: {html_path}")

        page.screenshot(path=str(path := save(b"", "_screenshot.png")), full_page=False)
        print(f"Screenshot saved: {path}")

        print(f"\n-- JSON API responses observed ({len(json_responses)}) --")
        for r in json_responses[:25]:
            print(f"  [{r['length']:>7,} B] {r['url'][:120]}")

        for i, r in enumerate(json_responses):
            body_path = save(r["body"].encode("utf-8"), f"_api_{i}.json")
            print(f"  saved: {body_path.name}")

        # Look for plan-like tokens in the rendered page
        tokens = sorted(set(re.findall(r"eco-\w+|general-\w+|standard-\w+|premium-\w+|medium-\w+", html)))
        print(f"\nPlan-like tokens in rendered HTML: {tokens[:30]}")

        browser.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
