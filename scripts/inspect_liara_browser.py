"""Fetch Liara's pages with a real browser (challenge/rendering may apply)."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from collectors.browser import launch_browser  # noqa: E402

EVIDENCE = ROOT / "evidence" / "liara" / "vm"
EVIDENCE.mkdir(parents=True, exist_ok=True)

URLS = {
    "product": "https://liara.ir/products/cloud-server/",
    "pricing": "https://liara.ir/pricing/",
}

KEYWORDS = ["vCPU", "vcpu", "RAM", "رم", "پردازنده", "تومان", "ریال", "گیگابایت", "IaaS", "iaas", "ماهانه"]


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    exit_code = 0
    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            for name, url in URLS.items():
                page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    page.wait_for_timeout(8_000)  # allow JS rendering
                    html = page.content()
                    path = EVIDENCE / f"{stamp}_{name}.html"
                    path.write_text(html, encoding="utf-8")
                    print(f"===== {name}: {url} =====")
                    print(f"HTTP {response.status if response else '?'}, {len(html):,} chars, evidence: {path.name}")
                    for kw in KEYWORDS:
                        c = html.count(kw)
                        if c:
                            print(f"  {kw!r}: {c}")
                    print(f"  <table> elements: {html.count('<table')}")
                    # count plan-like tokens
                    import re
                    tokens = sorted(set(re.findall(r"g\d-\w+|c\d-\w+|m\d-\w+|li-\w+|[a-z]+-\d{1,2}(?:-\d+)?", html)))
                    print(f"  plan-like tokens: {tokens[:25]}")
                except Exception as exc:
                    print(f"{name}: FAILED: {exc}")
                    exit_code = 1
                finally:
                    page.close()
        finally:
            browser.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
