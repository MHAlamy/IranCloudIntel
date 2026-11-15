"""Explore ParsPack's cloud-server calculator: controls, options, price display."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from collectors.browser import launch_browser  # noqa: E402

URL = "https://parspack.com/cloud-server"
EVIDENCE = ROOT / "evidence" / "parspack" / "vm"
EVIDENCE.mkdir(parents=True, exist_ok=True)


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(8_000)
            html = page.content()
            (EVIDENCE / f"{stamp}_rendered.html").write_text(html, encoding="utf-8")
            print(f"loaded: {page.title()} ({len(html):,} chars)")

            # form controls
            print("\n-- select controls --")
            for sel in page.locator("select").all()[:12]:
                options = sel.locator("option").all_inner_texts()[:12]
                print(f"  select: {options}")

            print("\n-- range sliders --")
            for inp in page.locator("input[type=range]").all()[:12]:
                print(f"  range: min={inp.get_attribute('min')} max={inp.get_attribute('max')} "
                      f"step={inp.get_attribute('step')} value={inp.input_value()}")

            print("\n-- number/text inputs --")
            for inp in page.locator("input[type=number], input[type=text]").all()[:12]:
                print(f"  input: type={inp.get_attribute('type')} name={inp.get_attribute('name')} "
                      f"value={inp.input_value()!r}")

            print("\n-- buttons with +/- like labels --")
            texts = ["ماه", "ساعتی", "ماهانه", "ساخت", "سرور", "لینوکس", "ویندوز"]
            for t in texts:
                count = page.get_by_text(t, exact=False).count()
                if count:
                    print(f"  text {t!r}: {count} matches")

            # find price display candidates
            print("\n-- price-ish text nodes --")
            import re
            body = page.inner_text("body")
            for line in body.split("\n"):
                if re.search(r"\d+.{0,3}(تومان|ریال)", line):
                    print(f"  {line.strip()[:100]}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
