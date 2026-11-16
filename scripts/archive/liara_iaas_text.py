"""Extract Liara's IaaS (سرور مجازی ابری) plan section from the pricing page."""

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SNAP = sorted((ROOT / "evidence" / "liara" / "vm").glob("*_pricing.html"))[-1]
soup = BeautifulSoup(SNAP.read_text(encoding="utf-8"), "html.parser")
text = soup.get_text("\n", strip=True)

# The IaaS section header
for marker in ("سرور مجازی ابری", "(IaaS)", "IaaS"):
    idx = text.find(marker)
    print(f"marker {marker!r} at: {idx}")

idx = text.find("سرور مجازی ابری")
if idx >= 0:
    print("\n--- text from the IaaS section onward (3000 chars) ---")
    print(text[idx:idx + 3000])
