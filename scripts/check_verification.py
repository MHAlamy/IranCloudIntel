"""Read-only check: rate storage and bundle-vs-rates verification results."""

import sys
from pathlib import Path

import sqlite3

sys.stdout.reconfigure(encoding="utf-8")
conn = sqlite3.connect(Path(__file__).resolve().parent.parent / "data" / "cloud_intel.db")
conn.row_factory = sqlite3.Row

print("-- verification status counts --")
for r in conn.execute(
    "SELECT rate_verification, COUNT(*) c FROM price_observations GROUP BY rate_verification"
):
    print(f"  {r['rate_verification']}: {r['c']}")

print("-- rates stored:", conn.execute("SELECT COUNT(*) c FROM resource_rates").fetchone()["c"])
print("-- rate rows (iran, first 40):")
for r in conn.execute(
    """SELECT category, unit, tier_label, amount_toman FROM resource_rates
       WHERE region='iran' ORDER BY id LIMIT 40"""
):
    print(f"  {r['category']:8} {r['unit']:14} {r['tier_label']:30} {r['amount_toman']}")

print("-- non-verified observations --")
for r in conn.execute(
    """SELECT off.plan_name, po.rate_verification, po.rate_verification_detail
       FROM price_observations po JOIN offerings off ON off.id = po.offering_id
       WHERE po.rate_verification != 'verified' LIMIT 10"""
):
    print(f"  {r['plan_name']}: {r['rate_verification']} | {r['rate_verification_detail'][:90]}")
