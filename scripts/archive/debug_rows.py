"""Debug: list all provider rows on each live dashboard view."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"

for query in ("tier=standard&size=medium", "tier=standard&size=large", "tier=standard&size=small"):
    text = httpx.get(f"{BASE}/vm?{query}").text
    providers = [ln.strip().replace('<td data-label="تأمین‌کننده">', "") for ln in text.split("\n") if 'data-label="تأمین‌کننده"' in ln]
    plans = [ln.strip() for ln in text.split("\n") if "plan-link" in ln]
    print(f"--- {query} ---")
    print("  providers:", providers)
    print("  plan links:", [p.split(">")[1].split("<")[0] for p in plans])
