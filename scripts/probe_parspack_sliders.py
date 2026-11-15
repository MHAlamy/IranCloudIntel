"""Systematic ParsPack calculator probe: slider position -> displayed value,
then baseline configs with daily/monthly prices."""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from collectors.browser import launch_browser

URL = "https://parspack.com/cloud-server"


def set_slider(page, slider, value):
    slider.evaluate(
        "(e, v) => { const proto = Object.getPrototypeOf(e); const setter = Object.getOwnPropertyDescriptor(proto, 'value').set; setter.call(e, String(v)); e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }",
        value,
    )
    page.wait_for_timeout(600)


def read_widget(page, sliders):
    widget_text = sliders[0].evaluate(
        "e => { let n = e; for (let i = 0; i < 8 && n.parentElement; i++) n = n.parentElement; return n.innerText; }"
    )
    lines = [ln.strip() for ln in widget_text.split("\n") if ln.strip()]
    return lines


def read_daily(page):
    body = page.inner_text("body")
    for line in body.split("\n"):
        if "روزانه" in line and "تومان" in line:
            return line.strip()
    return ""


def main() -> int:
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(6_000)
            sliders = page.locator("input[type=range]").all()

            names = {0: "RAM", 1: "disk", 2: "CPU"}
            mappings = {}
            for idx, slider in enumerate(sliders):
                mapping = []
                for pos in range(0, (slider.get_attribute("max") and int(slider.get_attribute("max")) or 0) + 1):
                    set_slider(page, slider, pos)
                    lines = read_widget(page, sliders)
                    # pattern: label (رم/فضا/پردازنده), then min, current, max
                    for i, ln in enumerate(lines):
                        if ln in ("رم", "فضا", "پردازنده") and i + 2 < len(lines):
                            current = lines[i + 2] if i + 2 <= len(lines) else ""
                            mapping.append((pos, current))
                            break
                # the read above is fragile; simpler: read middle column per pos
                mappings[idx] = mapping
                print(f"-- slider[{idx}] {names[idx]} position -> current display --")
                for pos, cur in mapping:
                    print(f"   {pos}: {cur}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
