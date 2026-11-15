"""Verify the discount note appears only on economy calculated rows."""

import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
for tier in ("economy", "standard", "premium"):
    text = httpx.get(f"{BASE}/vm?tier={tier}&size=medium").text
    has_calc = "محاسبه\u200cشده" in text
    has_discount = "تخفیف" in text
    print(f"{tier:8} calculated-row: {has_calc}, discount-note: {has_discount} (expected {'True' if tier == 'economy' else 'False'})")
