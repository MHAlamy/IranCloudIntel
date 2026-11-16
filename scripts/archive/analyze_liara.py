"""Analyze Liara's pricing page: find the IaaS plan structure (divs or JSON)."""

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SNAP = sorted((ROOT / "evidence" / "liara" / "vm").glob("*_pricing.html"))[-1]
html = SNAP.read_text(encoding="utf-8")
soup = BeautifulSoup(html, "html.parser")

print(f"snapshot: {SNAP.name}")

# embedded data markers
for marker in ("__NEXT_DATA__", "__NUXT__", "application/json", "window.__", "nuxt"):
    c = html.count(marker)
    if c:
        print(f"marker {marker!r}: {c}")

# plan-like tokens (Liara historically: g1-*, g2-*, li-*, c-* etc.)
tokens = re.findall(r"[a-z]{1,3}\d(?:\.\d)?-[a-z]+-?\d*", html)
from collections import Counter
common = Counter(tokens).most_common(30)
print("plan-like tokens:", common)

# find the IaaS section: locate a vCPU occurrence and dump surrounding text
text = soup.get_text("\n", strip=True)
idx = text.find("vCPU")
print("\n--- text around first 'vCPU' ---")
print(text[max(0, idx - 600):idx + 1500])
