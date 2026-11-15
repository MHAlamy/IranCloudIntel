"""Interact with ParsPack's calculator: set sliders, read resulting prices."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent)) if False else None
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from collectors.browser import launch_browser

URL = "https://parspack.com/cloud-server"


def slider_label(page, slider):
    """Best-effort label for a slider: nearby text within its container."""
    container = slider.evaluate(
        "e => { let n = e.closest('div'); let out = ''; for (let i = 0; i < 4 && n; i++) { out += ' ' + (n.innerText || ''); n = n.parentElement; } return out; }"
    )
    return " ".join(container.split())[:150]


def set_slider(page, slider, value):
    slider.evaluate(
        "(e, v) => { const proto = Object.getPrototypeOf(e); const setter = Object.getOwnPropertyDescriptor(proto, 'value').set; setter.call(e, String(v)); e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }",
        value,
    )
    page.wait_for_timeout(800)


def read_price(page):
    import re

    body = page.inner_text("body")
    prices = []
    for line in body.split("\n"):
        line = line.strip()
        if re.search(r"[\d۰-۹][\d۰-۹٬,]*.{0,3}(تومان|ریال)", line):
            prices.append(line[:90])
    return prices


def main() -> int:
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(6_000)

            sliders = page.locator("input[type=range]").all()
            print("sliders found:", len(sliders))
            for i, s in enumerate(sliders):
                print(f"  slider[{i}]: label≈{slider_label(page, s)!r}")

            # pick Iran + Tehran11 + Ubuntu (defaults may already be Iran)
            try:
                page.locator("select").nth(0).select_option(label="ایران")
                page.wait_for_timeout(1_000)
            except Exception as exc:
                print("location select:", exc)

            print("\n-- baseline slider combos --")
            combos = [
                ("small-ish (1/2/25 min disk)", ["1", "2", "0"]),
                ("medium (4/8/80?)", ["4", "8", "3"]),   # disk slider mapping unknown
                ("large-ish (16/32/300)", ["16", "32", "16"]),
            ]
            for name, values in combos:
                for i, v in enumerate(values):
                    if i < len(sliders):
                        set_slider(page, sliders[i], v)
                page.wait_for_timeout(1_500)
                print(f"\n[{name}] slider positions={values}")
                # dump the calculator widget text (container holding the sliders)
                try:
                    widget_text = sliders[0].evaluate(
                        "e => { let n = e; for (let i = 0; i < 8 && n.parentElement; i++) n = n.parentElement; return n.innerText; }"
                    )
                    for line in widget_text.split("\n"):
                        line = line.strip()
                        if line:
                            print(f"   | {line[:100]}")
                except Exception as exc:
                    print("   widget read failed:", exc)
                for price in read_price(page)[:6]:
                    print(f"   $ {price}")

            # also try monthly toggle if present
            try:
                page.get_by_text("ماهانه", exact=True).first.click()
                page.wait_for_timeout(1_500)
                print("\n[after clicking ماهانه]")
                for price in read_price(page)[:6]:
                    print(f"   {price}")
            except Exception as exc:
                print("monthly toggle:", exc)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
