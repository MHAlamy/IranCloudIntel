"""Fetch and inspect Kubit's pricing page (plain HTTP first)."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence" / "kubit" / "vm"
EVIDENCE.mkdir(parents=True, exist_ok=True)

URL = "https://kubit.cloud/fa/pricing"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

KEYWORDS = [
    "vCPU", "vcpu", "CPU", "RAM", "رم", "پردازنده", "تومان", "ریال",
    "گیگابایت", "ابری", "IaaS", "iaas", "ماهانه", "ساعتی", "سرور",
]


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    response = httpx.get(
        URL,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "fa,en;q=0.8"},
        timeout=30.0,
        follow_redirects=True,
    )
    html = response.text
    path = EVIDENCE / f"{stamp}_pricing_http.html"
    path.write_text(html, encoding="utf-8")
    print(f"HTTP {response.status_code}, final URL: {response.url}")
    print(f"HTML: {len(html):,} chars, evidence: {path.name}")
    for kw in KEYWORDS:
        c = html.count(kw)
        if c:
            print(f"  {kw!r}: {c}")
    print(f"  <table> elements: {html.count('<table')}")
    import re
    tokens = sorted(set(re.findall(r"[a-z]+-[a-z]*\d{1,2}(?:-[a-z0-9]+)*", html)))
    print(f"  plan-like tokens: {tokens[:25]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
