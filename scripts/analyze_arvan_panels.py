"""Extract the three pricing tab panels from Arvan's rendered page.

The page server-renders all three panels (basic/standard/premium) and toggles
visibility with Alpine.js x-show. This script locates each panel in the saved
snapshot and prints its plan names, prices and resource labels.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "evidence" / "arvan" / "cloud-server"
SNAPSHOT = sorted(EVIDENCE_DIR.glob("*_*_tab_economy.html"))[-1]

PANEL_MATCH_RE = re.compile(r"active === '(basic|standard|premium)'")


def main() -> None:
    soup = BeautifulSoup(SNAPSHOT.read_text(encoding="utf-8"), "html.parser")

    for tab in ("basic", "standard", "premium"):
        panels = [
            el for el in soup.find_all(attrs={"x-show": PANEL_MATCH_RE})
            if f"active === '{tab}'" in (el.get("x-show") or "")
        ]
        # Panels that are plan containers (not the tab-header highlight)
        print(f"===== tab '{tab}': {len(panels)} x-show panel(s) =====")
        for el in panels:
            classes = " ".join(el.get("class", []))
            text = el.get_text("\n", strip=True)
            # Compact: collapse blank lines
            lines = [ln for ln in text.split("\n") if ln.strip()]
            print(f"  <{el.name} class='{classes[:80]}'> — {len(lines)} non-empty text lines")
            # Show a compact digest: plan-like tokens and price patterns
            joined = "\n".join(lines)
            tokens = sorted(set(re.findall(r"[a-z]+-[a-z]+\d+", joined)))
            prices = re.findall(r"[\d۰-۹]+(?:[٬,][\d۰-۹]{3})+", joined)
            print(f"    plan-like tokens: {tokens[:20]}")
            print(f"    price-like numbers: {prices[:20]}")
        print()


if __name__ == "__main__":
    main()
