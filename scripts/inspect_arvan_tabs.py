"""Capture each of Arvan's pricing tabs independently.

Builds on the finding that the cloud-server pricing page renders tab content
on click. Enumerates tab-like elements, clicks each tab, and saves one
rendered snapshot per tab. No LLM calls; public page only; evidence under
evidence/ (gitignored).
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.arvancloud.ir/fa/pricing/cloud-server"
EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "evidence" / "arvan" / "cloud-server"

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# Substrings that survive Persian spelling variants (strip first/last char).
TAB_LABEL_FRAGMENTS = ["اندارد", "قتصادی", "میوم", "Premium", "Standard", "Economy"]
PLAN_TOKEN_RE = r"eco-\w+|general-\w+|standard-\w+|premium-\w+|medium-\w+"


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def save(content: bytes, name: str) -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()[:12]
    path = EVIDENCE_DIR / f"{stamp()}_{digest}_{name}"
    path.write_bytes(content)
    return path


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60_000)

        # Wait for real content
        for _ in range(12):
            page.wait_for_timeout(5_000)
            if page.locator("text=eco-small").count() > 0:
                break
        print(f"Loaded: {page.title()} ({len(page.content()):,} chars)")

        # Find candidate tab elements by label fragments
        candidates: list[dict] = []
        seen = set()
        for fragment in TAB_LABEL_FRAGMENTS:
            for el in page.locator(f"text={fragment}").all():
                box = el.bounding_box()
                if box is None:
                    continue
                tag = el.evaluate("e => e.tagName")
                classes = el.evaluate("e => e.className")
                text = el.inner_text().strip().replace("\n", " | ")
                key = (tag, str(classes), text)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({"tag": tag, "classes": str(classes)[:120], "text": text[:80],
                                   "x": box["x"], "y": box["y"]})

        print(f"\n-- Candidate tab elements ({len(candidates)}) --")
        for c in candidates:
            print(f"  <{c['tag']}> x={c['x']:.0f} y={c['y']:.0f} class={c['classes']} text={c['text']!r}")

        # Persist the DOM inventory for analysis
        report = "\n".join(
            f"<{c['tag']}> x={c['x']:.0f} y={c['y']:.0f} class={c['classes']} text={c['text']!r}"
            for c in candidates
        )
        print(f"\nInventory saved: {save(report.encode('utf-8'), 'tab_inventory.txt')}")

        browser.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
