"""Fetch and inspect Liara's cloud-server product and pricing pages.

Milestone 4, first increment: determine which page carries the VM/IaaS price
table and how it is delivered (static HTML vs JS-rendered). Saves raw
evidence under evidence/liara/vm/. Free operation: plain HTTP, no LLM.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence" / "liara" / "vm"
EVIDENCE.mkdir(parents=True, exist_ok=True)

URLS = {
    "product": "https://liara.ir/products/cloud-server/",
    "pricing": "https://liara.ir/pricing/",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

KEYWORDS = [
    "vCPU", "vcpu", "CPU", "RAM", "رم", "پردازنده",
    "تومان", "ریال", "گیگابایت", "ابری", "IaaS", "iaas",
    "cloud-server", "monthly", "ماهانه",
]


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "fa,en;q=0.8"}, timeout=30.0, follow_redirects=True) as client:
        for name, url in URLS.items():
            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                print(f"{name}: FETCH FAILED: {exc}")
                continue
            html = response.text
            path = EVIDENCE / f"{stamp}_{name}.html"
            path.write_text(html, encoding="utf-8")

            print(f"===== {name}: {url} =====")
            print(f"HTTP {response.status_code}, {len(html):,} chars, evidence: {path.name}")
            for kw in KEYWORDS:
                count = html.count(kw)
                if count:
                    print(f"  {kw!r}: {count}")
            # real <table> elements?
            tables = html.count("<table")
            print(f"  <table> elements: {tables}")
            print()


if __name__ == "__main__":
    main()
