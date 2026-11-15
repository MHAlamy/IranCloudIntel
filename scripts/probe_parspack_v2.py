"""Probe all three ParsPack sliders with a robust triple-value reader."""

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
    page.wait_for_timeout(500)


def read_currents(page, sliders):
    """Return {ram, disk, cpu, daily} parsed from the widget + page text."""
    widget_text = sliders[0].evaluate(
        "e => { let n = e; for (let i = 0; i < 8 && n.parentElement; i++) n = n.parentElement; return n.innerText; }"
    )
    lines = [ln.strip() for ln in widget_text.split("\n") if ln.strip()]
    currents = {}
    labels = {"رم": "ram", "فضا": "disk", "پردازنده": "cpu"}
    for i, ln in enumerate(lines):
        if ln in labels and i + 2 < len(lines):
            key = labels[ln]
            if key not in currents:
                currents[key] = lines[i + 2]
    body = page.inner_text("body")
    daily = ""
    for line in body.split("\n"):
        if "روزانه" in line and "تومان" in line:
            daily = line.strip()
            break
    return currents, daily


def main() -> int:
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(6_000)
            sliders = page.locator("input[type=range]").all()

            print("-- disk slider (slider[1]) positions --")
            for pos in range(0, 17):
                set_slider(page, sliders[1], pos)
                currents, daily = read_currents(page, sliders)
                print(f"   pos {pos:2}: {currents} | {daily}")

            print("-- CPU slider (slider[2]) positions --")
            for pos in range(0, 17):
                set_slider(page, sliders[2], pos)
                currents, daily = read_currents(page, sliders)
                print(f"   pos {pos:2}: {currents} | {daily}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
