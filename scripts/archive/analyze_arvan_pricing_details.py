"""Deep-dive into Arvan's rendered pricing snapshot: what pricing information
exists beyond the bundle table (per-component CPU/memory rates, PAYG rates).
Offline analysis of the saved snapshot only."""

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "evidence" / "arvan" / "vm" / "20261115T083700Z_889543239d62" / "rendered.html"

soup = BeautifulSoup(SNAP.read_text(encoding="utf-8"), "html.parser")

# 1) Full price cell content of the first row (index 4) — what did we truncate?
print("===== price cell of first row (full text, line by line) =====")
first_tr = soup.find("tr", onclick=re.compile("eco-small1"))
if first_tr:
    cells = first_tr.find_all("td")
    for i, cell in enumerate(cells):
        text_lines = [ln.strip() for ln in cell.get_text("\n").split("\n") if ln.strip()]
        print(f"td[{i}]: {text_lines}")

# 2) Every distinct text line on the page that contains a number followed by
#    currency, with nearby label hints (searching for component/unit rates)
print("\n===== all price-bearing lines on the page (deduped, in order) =====")
body_text = soup.get_text("\n", strip=True)
lines = body_text.split("\n")
price_re = re.compile(r"[\d۰-۹]+(?:[٬,][\d۰-۹]{3})*")
seen = set()
for i, ln in enumerate(lines):
    if price_re.search(ln) and any(cur in ln for cur in ("تومان", "ریال")):
        key = ln.strip()
        if key not in seen:
            seen.add(key)
            context = " < ".join(x.strip() for x in lines[max(0, i - 2):i] if x.strip()[-2:])
            print(f"  {key[:70]:70} | context: {context[:90]}")

# 3) Section headings on the page (to map where each pricing block lives)
print("\n===== headings / section titles =====")
for h in soup.find_all(["h1", "h2", "h3", "h4"]):
    text = h.get_text(" ", strip=True)
    if text:
        print(f"  <{h.name}> {text[:100]}")
