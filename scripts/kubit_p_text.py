"""Read the text around Kubit's P-ladder table with proper UTF-8 output."""

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SNAP = sorted((ROOT / "evidence" / "kubit" / "vm").glob("*_pricing_http.html"))[-1]
soup = BeautifulSoup(SNAP.read_text(encoding="utf-8"), "html.parser")

text = soup.get_text("\n", strip=True)
idx = text.find("P = 2")
print("--- text around the P formula ---")
print(text[max(0, idx - 1200):idx + 900])
