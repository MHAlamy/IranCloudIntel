"""Capture each of Arvan's three pricing tabs independently (economy, standard, premium).

The page uses Alpine.js: tab controls are div.cursor-pointer elements with
@click="changeTab('<tab>')". Clicking the inner <p> does nothing; we click the
control div itself and wait until the pricing container's text actually changes.

Evidence under evidence/ (gitignored). No LLM calls; public page only.
"""

from __future__ import annotations

import hashlib
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

PLAN_TOKEN_RE = re.compile(r"eco-\w+|general-\w+|standard-\w+|premium-\w+|medium-\w+")

TABS = [
    ("economy", None),  # active by default (x-data="pricingTable('basic')")
    ("standard", "بسته‌های استاندارد"),
    ("premium", "بسته‌های پریمیوم"),
]


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save(content: bytes, name: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()[:12]
    path = EVIDENCE_DIR / f"{stamp()}_{digest}_{name}"
    path.write_bytes(content)
    return path


def scope_fingerprint(page) -> str:
    """Fingerprint of the Alpine pricing container only (avoids dynamic noise elsewhere)."""
    container = page.locator("xpath=//div[starts-with(@x-data,'pricingTable')]").first
    return hashlib.sha256(container.inner_text().encode("utf-8")).hexdigest()


def plan_tokens(html: str) -> list[str]:
    return sorted(set(PLAN_TOKEN_RE.findall(html)))


def main() -> None:
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60_000)

        for _ in range(12):
            page.wait_for_timeout(5_000)
            if page.locator("text=eco-small").count() > 0:
                break

        previous_fingerprint = scope_fingerprint(page)

        for tab_name, click_text in TABS:
            if click_text is not None:
                control = page.locator("div.cursor-pointer", has_text=click_text).first
                control.scroll_into_view_if_needed()
                control.click(timeout=10_000)
                changed = False
                for _ in range(10):
                    page.wait_for_timeout(2_000)
                    if scope_fingerprint(page) != previous_fingerprint:
                        changed = True
                        break
                print(f"[{tab_name}] clicked control for {click_text!r}; content changed: {changed}")
            else:
                print(f"[{tab_name}] initial active tab")

            page.wait_for_timeout(2_000)  # settle
            html = page.content()
            tokens = plan_tokens(html)
            previous_fingerprint = scope_fingerprint(page)

            path = save(html.encode("utf-8"), f"tab_{tab_name}.html")
            print(f"    tokens: {tokens}")
            print(f"    saved: {path.name} ({len(html):,} chars)")

        browser.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
