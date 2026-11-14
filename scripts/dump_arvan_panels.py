"""Dump full panel text from the latest Arvan economy snapshot (design aid)."""

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

EVIDENCE = Path(__file__).resolve().parent.parent / "evidence" / "arvan" / "cloud-server"
snap = sorted(EVIDENCE.glob("*_*_tab_economy.html"))[-1]
soup = BeautifulSoup(snap.read_text(encoding="utf-8"), "html.parser")
panel_re = re.compile(r"active === '(basic|standard|premium)'")

for tab in ("basic", "standard", "premium"):
    for el in soup.find_all(attrs={"x-show": panel_re}):
        if f"active === '{tab}'" not in (el.get("x-show") or ""):
            continue
        lines = [ln.strip() for ln in el.get_text("\n", strip=True).split("\n") if ln.strip()]
        print(f"===== {tab} ({len(lines)} lines) =====")
        for i, ln in enumerate(lines):
            print(f"{i:2}: {ln}")
        print()
