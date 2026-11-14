"""Fetching for Playwright-based sources, currently Arvan.

Handles the JavaScript anti-bot challenge by rendering with a real browser
(browser choice is environment-configurable; see collectors/browser.py) and
waits until a configurable readiness marker proves real content rendered.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from collectors.browser import launch_browser  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


class FetchError(RuntimeError):
    """Raised when the page cannot be fetched or real content never appears."""


@dataclass
class FetchResult:
    html: str
    http_status: int | None
    final_url: str


def fetch_with_browser(
    url: str,
    ready_marker: str,
    max_wait_seconds: int = 60,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    locale: str = "fa-IR",
) -> FetchResult:
    """Render `url` in the configured browser and wait for `ready_marker` text."""
    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            page = browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height}, locale=locale
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            marker_seen = False
            elapsed = 0
            while elapsed < max_wait_seconds:
                page.wait_for_timeout(5_000)
                elapsed += 5
                if ready_marker and page.locator(f"text={ready_marker}").count() > 0:
                    marker_seen = True
                    break
            if ready_marker and not marker_seen:
                raise FetchError(
                    f"content marker {ready_marker!r} not seen within {max_wait_seconds}s on {url}"
                )
            html = page.content()
            return FetchResult(
                html=html,
                http_status=response.status if response else None,
                final_url=page.url,
            )
        finally:
            browser.close()
