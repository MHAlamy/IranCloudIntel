"""Verify the discount note does not appear on Kubit (factor 1.0) rows."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

text = httpx.get("http://127.0.0.1:8000/vm?tier=economy&size=small").text
kubit_section = text.split("Kubit", 1)[-1]
arvan_section = text.split("Kubit", 1)[0]

print("Arvan economy rows keep the discount note:", "تخفیف" in arvan_section)
print("Kubit economy row has NO discount note:", "تخفیف" not in kubit_section)
print("Kubit row present with calculated basis:", ("Kubit" in text) and ("محاسبه\u200cشده" in kubit_section))
