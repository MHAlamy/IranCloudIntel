"""Examine the DOM structure around Arvan's pricing tab labels to find the
real interactive elements. Offline analysis of the saved economy snapshot."""

from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "evidence" / "arvan" / "cloud-server"
SNAPSHOT = sorted(EVIDENCE_DIR.glob("*_*_tab_economy.html"))[-1]

LABELS = ["بسته‌های استاندارد", "بسته‌های پریمیوم"]


def describe(el, depth: int = 4) -> str:
    parts = []
    current = el
    for i in range(depth):
        if current is None or current.name is None:
            break
        classes = " ".join(current.get("class", []))[:100]
        attrs = {k: v for k, v in current.attrs.items() if k != "class"}
        parts.append(f"{'  ' * i}<{current.name} class='{classes}' {attrs}>")
        current = current.parent
    return "\n".join(parts)


def main() -> None:
    soup = BeautifulSoup(SNAPSHOT.read_text(encoding="utf-8"), "html.parser")
    text_nodes = soup.find_all(string=True)
    for label in LABELS:
        print(f"===== {label!r} =====")
        hits = [s.parent for s in text_nodes if s and label in (s.string or "")]
        print(f"matches: {len(hits)}")
        for el in hits[:3]:
            print(describe(el))
            print()


if __name__ == "__main__":
    main()
