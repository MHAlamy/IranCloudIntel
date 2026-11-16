"""Check live DB contents per provider (read-only)."""

import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
conn = sqlite3.connect(Path(__file__).resolve().parent.parent / "data" / "cloud_intel.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """SELECT p.slug, COUNT(*) AS c FROM price_observations po
       JOIN offerings o ON o.id = po.offering_id
       JOIN providers p ON p.id = o.provider_id GROUP BY p.slug"""
).fetchall()
print("observations by provider:", [(r["slug"], r["c"]) for r in rows])
rates = conn.execute(
    """SELECT p.slug, COUNT(*) AS c FROM resource_rates r
       JOIN providers p ON p.id = r.provider_id GROUP BY p.slug"""
).fetchall()
print("rates by provider:", [(r["slug"], r["c"]) for r in rates])
