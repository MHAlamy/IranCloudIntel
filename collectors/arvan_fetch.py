"""Fetching for Playwright-based sources, currently Arvan.

Handles the JavaScript anti-bot challenge by rendering with a real browser
(browser choice is environment-configurable; see collectors/browser.py) and
waits until a configurable readiness marker proves real content rendered.
"""

from __future__ import annotations

import sys
from pathlib import Path


from playwright.sync_api import sync_playwright  # noqa: E402

from collectors.browser import launch_browser  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


from collectors.common import FetchError, FetchResult


def fetch_with_browser(
    url: str,
    ready_marker: str,
    click_selector: str | None = None,
    max_wait_seconds: int = 60,
    viewport_width: int = 1440,
    viewport_height: int = 900,
    locale: str = "fa-IR",
) -> FetchResult:
    """Render `url` in the configured browser and wait for `ready_marker` text.

    `click_selector` (optional) is clicked after load and before the marker
    wait — for pages whose pricing content renders only after a client-side
    tab switch (e.g. Hamravesh's pricing menu).
    """
    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            page = browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height}, locale=locale
            )
            response = page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            page.set_default_timeout(max_wait_seconds * 1000)
            if click_selector:
                page.locator(click_selector).first.click()
            if ready_marker:
                page.get_by_text(ready_marker, exact=False).first.wait_for(state='attached')
            html = page.content()
            return FetchResult(
                html=html,
                http_status=response.status if response else None,
                final_url=page.url,
            )
        finally:
            browser.close()
