"""Extract Arvan's component rate table with exact labels (offline analysis)."""

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "evidence" / "arvan" / "vm" / "20261115T083700Z_889543239d62" / "rendered.html"
soup = BeautifulSoup(SNAP.read_text(encoding="utf-8"), "html.parser")

# Find the element containing 'هر vCore' and dump its enclosing table/section
anchor = soup.find(string=re.compile("هر vCore"))
if anchor is None:
    print("anchor not found")
    sys.exit(1)

# Walk up to the enclosing table
table = anchor.find_parent("table")
print("===== enclosing <table> structure =====")
if table:
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        print("  |", " | ".join(cells))
else:
    # maybe div-based; dump the enclosing section text structure
    section = anchor.find_parent(["section", "div"])
    print(section.get_text("\n", strip=True)[:3000])

# Footnotes / explanatory text around the rate table
parent_section = anchor.find_parent(class_=re.compile("section|container|row"))
if parent_section:
    print("\n===== text of the enclosing section (first 2500 chars) =====")
    print(parent_section.get_text("\n", strip=True)[:2500])

# All table headers on the page (to locate all pricing tables)
print("\n===== all tables on the page (header rows) =====")
for i, t in enumerate(soup.find_all("table")):
    head = t.find("tr")
    cells = [c.get_text(" ", strip=True) for c in head.find_all(["th", "td"])] if head else []
    rows = len(t.find_all("tr"))
    print(f"  table[{i}] rows={rows} header={cells[:8]}")
