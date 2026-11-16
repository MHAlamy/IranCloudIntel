"""Live verification: Liara reflected on the running dashboard."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

results = {}
for tier, size, expected_plan, expected_price in [
    ("standard", "small", "مشتری", 1675000),
    ("standard", "medium", "اورانوس", 4800000),
    ("standard", "large", "پلوتون", 14200000),
    ("standard", "very_large", "اریس", 24800000),
]:
    text = httpx.get(f"{BASE}/vm?tier={tier}&size={size}").text
    has_plan = expected_plan in text
    has_price = fa(expected_price) in text
    results[f"{tier}/{size}: {expected_plan} @ {fa(expected_price)}"] = has_plan and has_price

for key, ok in results.items():
    print(("✓" if ok else "✗"), key)

print("health:", httpx.get(f"{BASE}/health").json())
