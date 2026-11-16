"""Fresh-instance verification: ordering, Liara content, health."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
names = ["ArvanCloud", "Liara", "ParsPack", "Kubit"]

print("health:", httpx.get(f"{BASE}/health").json())
for size in ("small", "medium", "large", "very_large"):
    t = httpx.get(f"{BASE}/vm?tier=standard&size={size}").text
    pos = [t.find(n) for n in names]
    ok = pos == sorted(pos) and all(p >= 0 for p in pos)
    print(f"standard/{size}: order {pos} sorted={ok}")

t = httpx.get(f"{BASE}/vm?tier=standard&size=medium").text
fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
print("Liara اورانوس ۴٬۸۰۰٬۰۰۰:", fa(4800000) in t)
print("ParsPack ۳٬۴۰۸٬۱۲۰:", fa(3408120) in t)
print("Arvan ۵٬۰۲۴٬۸۸۰:", fa(5024880) in t)
print("Kubit ۵٬۰۳۹٬۰۸۰:", fa(5039080) in t)
