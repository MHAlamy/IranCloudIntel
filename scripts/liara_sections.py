"""Locate Liara's IaaS plan table: section order on pricing page + product page."""

import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def section_map(text: str) -> list[str]:
    markers = ["(PaaS)", "(DBaaS)", "(IaaS)", "سرور مجازی ابری", "(Email)", "هوش مصنوعی",
               "(Wordpress)", "Object Storage", "ذخیره‌سازی ابری"]
    out = []
    for m in markers:
        pos = 0
        while True:
            idx = text.find(m, pos)
            if idx < 0:
                break
            out.append((idx, m))
            pos = idx + 1
    return sorted(out)


for name in ("pricing", "product"):
    snaps = sorted((ROOT / "evidence" / "liara" / "vm").glob(f"*_{name}.html"))
    soup = BeautifulSoup(snaps[-1].read_text(encoding="utf-8"), "html.parser")
    text = soup.get_text("\n", strip=True)
    print(f"===== {name} ({snaps[-1].name}) =====")
    for idx, m in section_map(text):
        print(f"  {idx:>7,}  {m}")

    if name == "product":
        idx = text.find("vCPU")
        print("\n--- product page text around first vCPU ---")
        print(text[max(0, idx - 1200):idx + 1600])
    else:
        # where does the LAST (PaaS/DBaaS) planet table end? what sections follow?
        idx = text.rfind("پلوتون")
        print("\n--- pricing page: text after the last پلوتون table (1200 chars) ---")
        print(text[idx:idx + 1200])
    print()
