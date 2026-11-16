"""Live verification: ParsPack reflected on the running dashboard."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

standard_medium = httpx.get(f"{BASE}/vm?tier=standard&size=medium").text
standard_small = httpx.get(f"{BASE}/vm?tier=standard&size=small").text
standard_large = httpx.get(f"{BASE}/vm?tier=standard&size=large").text
standard_vl = httpx.get(f"{BASE}/vm?tier=standard&size=very_large").text

print("health:", httpx.get(f"{BASE}/health").json())
print(" ParsPack on standard/medium:", "ParsPack" in standard_medium)
print(" ParsPack Medium exact quote ۳٬۴۰۸٬۱۲۰:", fa(3408120) in standard_medium)
print(" ParsPack adjustment note (IPv4 + 5%):", "تخفیف خرید ماهانه" in standard_medium)
print(" ParsPack Small near-miss ۱٬۲۲۷٬۳۰۰:", fa(1227300) in standard_small)
print(" ParsPack Large near-miss ۱۲٬۶۴۷٬۸۲۰:", fa(12647820) in standard_large)
print(" ParsPack VeryLarge near-miss ۲۴٬۳۴۹٬۰۶۵:", fa(24349065) in standard_vl)
print(" Kubit still present (standard/medium):", fa(5039080) in standard_medium)
print(" Arvan still present (standard/medium):", fa(1431720) in standard_medium)
