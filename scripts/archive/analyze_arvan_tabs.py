"""Analyze captured Arvan tab snapshots: what changed between tabs, and what
price-bearing text is visible. Offline analysis of saved evidence only."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "evidence" / "arvan" / "cloud-server"


def visible_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def main() -> None:
    files = {}
    for name in ("economy", "standard", "premium"):
        matches = sorted(EVIDENCE_DIR.glob(f"*_*_tab_{name}.html"))
        if matches:
            files[name] = matches[-1]

    texts = {k: visible_text(v) for k, v in files.items()}
    for k, t in texts.items():
        print(f"{k}: {len(t):,} visible chars, from {files[k].name}")

    # Lines containing currency/price signals
    price_line_re = re.compile(r"(تومان|ریال|Toman|Rial)", re.UNICODE)
    for name, text in texts.items():
        lines = [ln for ln in text.split("\n") if price_line_re.search(ln)]
        print(f"\n===== {name}: {len(lines)} price-bearing lines (first 25) =====")
        for ln in lines[:25]:
            print(f"  {ln[:120]}")

    # What differs between economy and standard visible text?
    if "economy" in texts and "standard" in texts:
        import difflib
        diff = [
            ln for ln in difflib.unified_diff(
                texts["economy"].split("\n"),
                texts["standard"].split("\n"),
                lineterm="", n=0,
            )
            if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))
        ]
        print(f"\n===== diff economy->standard: {len(diff)} changed lines (first 40) =====")
        for ln in diff[:40]:
            print(f"  {ln[:140]}")


if __name__ == "__main__":
    main()
