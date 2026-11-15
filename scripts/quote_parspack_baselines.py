"""Quote ParsPack baseline configurations: exact prices for closest-to-baseline configs."""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright

from collectors.browser import launch_browser

URL = "https://parspack.com/cloud-server"

# slider indices: [0]=RAM, [1]=disk, [2]=CPU
RAM_POS = {2: 0, 4: 1, 8: 2, 16: 3, 32: 4, 64: 5}
DISK_POS = {gb: (gb - 25) // 5 for gb in range(25, 106, 5)}
CPU_POS = {c: c - 1 for c in range(1, 17)}
CPU_POS[32] = 16


def set_slider(page, slider, value):
    slider.evaluate(
        "(e, v) => { const proto = Object.getPrototypeOf(e); const setter = Object.getOwnPropertyDescriptor(proto, 'value').set; setter.call(e, String(v)); e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); }",
        value,
    )
    page.wait_for_timeout(500)


def read_quote(page):
    """Return the live daily quote: a 'N تومان' line directly after 'روزانه:'."""
    body = page.inner_text("body")
    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    price_line = re.compile(r"^[۰-۹0-9٬,]+ تومان$")
    for i, ln in enumerate(lines):
        if ln == "روزانه:" and i + 1 < len(lines) and price_line.match(lines[i + 1]):
            return lines[i + 1]
    for i, ln in enumerate(lines):
        if "روزانه" in ln and i + 1 < len(lines) and price_line.match(lines[i + 1]):
            return lines[i + 1]
    return "?"


def read_currents(page, sliders):
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
    return currents


def main() -> int:
    configs = [
        ("Small baseline 1 vCPU / 2 GB / 20 GB → closest (1/2/25)", (0, 0, 0)),
        ("Medium baseline 4/8/80 → EXACT (4/8/80)", (RAM_POS[8], DISK_POS[80], CPU_POS[4])),
        ("Large baseline 16/32/320 → closest (16/32/disk-max)", (RAM_POS[32], 26, CPU_POS[16])),
        ("VeryLarge baseline 32/64/640 → closest (32/64/disk-max)", (RAM_POS[64], 26, CPU_POS[32])),
    ]
    with sync_playwright() as p:
        browser = launch_browser(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(6_000)
            sliders = page.locator("input[type=range]").all()

            for name, (ram_pos, disk_pos, cpu_pos) in configs:
                set_slider(page, sliders[0], ram_pos)
                set_slider(page, sliders[1], disk_pos)
                set_slider(page, sliders[2], cpu_pos)
                page.wait_for_timeout(1_200)
                currents = read_currents(page, sliders)
                quote = read_quote(page)
                print(f"\n== {name}")
                print(f"   actual config: {currents}")
                print(f"   daily quote:   {quote}")

            # billing-period options near the quote
            print("\n-- elements mentioning ماهانه / ساعتی --")
            for el in page.locator("text=ماهانه").all()[:6]:
                print(f"   <{el.evaluate('e => e.tagName')}> {el.inner_text()[:60]!r}")
            for el in page.locator("text=ساعتی").all()[:6]:
                print(f"   <{el.evaluate('e => e.tagName')}> {el.inner_text()[:60]!r}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
