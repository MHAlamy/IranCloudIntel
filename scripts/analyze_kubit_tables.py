"""Extract Kubit's IaaS/VM pricing table from the saved HTTP snapshot."""

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SNAP = sorted((ROOT / "evidence" / "kubit" / "vm").glob("*_pricing_http.html"))[-1]
soup = BeautifulSoup(SNAP.read_text(encoding="utf-8"), "html.parser")

print(f"snapshot: {SNAP.name}")

for i, table in enumerate(soup.find_all("table")):
    rows = table.find_all("tr")
    # render a compact digest of each table
    lines = []
    for tr in rows[:12]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        lines.append(" | ".join(cells))
    digest = "\n".join(lines)
    if any(k in digest for k in ("vCPU", "رم", "تومان", "IaaS", "پردازنده")):
        print(f"===== table[{i}] ({len(rows)} rows) =====")
        print(digest[:1800])
        print()
