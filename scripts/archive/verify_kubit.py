"""Live verification: Kubit reflected on the running dashboard."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

economy = httpx.get(f"{BASE}/vm?tier=economy&size=medium").text
standard = httpx.get(f"{BASE}/vm?tier=standard&size=medium").text
premium = httpx.get(f"{BASE}/vm?tier=premium&size=medium").text
small = httpx.get(f"{BASE}/vm?tier=economy&size=small").text

print("economy/medium  Kubit present:", "Kubit" in economy)
print("economy/medium  Kubit gen-3 Medium ۳٬۸۹۵٬۰۸۰:", fa(3895080) in economy)
print("standard/medium Kubit gen-4 Medium ۵٬۰۳۹٬۰۸۰:", fa(5039080) in standard)
print("economy/small   Kubit gen-3 Small ۱٬۱۰۳٬۵۲۰:", fa(1103520) in small)
print("premium/medium  no Kubit row:", fa(5039080) not in premium and fa(3895080) not in premium)
print("health:", httpx.get(f"{BASE}/health").json())
