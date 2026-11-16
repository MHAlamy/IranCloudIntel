"""Inspect the DOM structure of Arvan's PAYG rate section (panes, region tabs)."""

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "evidence" / "arvan" / "vm" / "20261115T083700Z_889543239d62" / "rendered.html"
soup = BeautifulSoup(SNAP.read_text(encoding="utf-8"), "html.parser")


def ancestry(el, depth=6):
    out = []
    cur = el
    for _ in range(depth):
        if cur is None or cur.name is None:
            break
        classes = " ".join(cur.get("class", []))[:110]
        attrs = {k: str(v)[:80] for k, v in cur.attrs.items() if k != "class"}
        out.append(f"<{cur.name} class='{classes}' {attrs}>")
        cur = cur.parent
    return "\n  ".join(out)


for label in ["هر vCore", "هر vCPU", "بلاک استوریج (Eco)", "به‌ازای IPv4 اول"]:
    print(f"===== {label!r} =====")
    node = soup.find(string=re.compile(re.escape(label)))
    if node is None:
        print("  NOT FOUND")
        continue
    print("  " + ancestry(node.parent, 7))
    # pane region hints: look for x-show/x-data/region markers up the tree
    cur = node.parent
    for _ in range(10):
        if cur is None or cur.name is None:
            break
        joined = " ".join(str(v) for k, v in cur.attrs.items())
        if any(m in joined.lower() for m in ("iran", "europe", "tab", "x-show", "x-data")):
            print(f"    [ancestor attr hint] <{cur.name} {joined[:160]}>")
        cur = cur.parent
    print()
