"""Live verification of the running dashboard."""

import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"

print("health:", httpx.get(f"{BASE}/health").status_code)
font = httpx.get(f"{BASE}/static/fonts/Vazirmatn-Regular.woff2")
print("regular font:", font.status_code, len(font.content), "bytes")

t = httpx.get(f"{BASE}/vm?tier=standard&size=small").text
print("standard/small -> calculated ۱٬۴۳۱٬۷۲۰ present:", "۱٬۴۳۱٬۷۲۰" in t)
print("standard/small -> g3-small1 dropped:", "g3-small1" not in t)
print("standard/small -> no verification badge:", "تأیید" not in t)
print("no region column:", "منطقه" not in t)
print("iran-only note:", "تنها برای مناطق ایران" in t)
print("bidi span present:", 'dir="ltr"' in t)

t2 = httpx.get(f"{BASE}/vm?tier=economy&size=medium").text
print("economy/medium -> calculated ۳٬۴۷۸٬۳۲۰ present:", "۳٬۴۷۸٬۳۲۰" in t2)
print("economy/medium -> approximate g1-medium1 dropped:", "g1-medium1" not in t2)
print("date-only last-checked (no ۱۳:۳۰ time):", "۱۳:۳۰" not in t2)
