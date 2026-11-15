"""Recompute rate_verification for the latest observations using stored rates.

Derived metadata only — never touches raw price history. Free (no LLM, no fetch).
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.pipeline import _tier_rates_from_repo  # noqa: E402
from comparison.matching import is_iranian_region  # noqa: E402
from comparison.rate_check import load_rate_mappings, verify_bundle  # noqa: E402
from storage.repository import Repository  # noqa: E402

repo = Repository(ROOT / "data" / "cloud_intel.db")
mappings = load_rate_mappings()
try:
    mapping = mappings.get("arvan")
    lookup = _tier_rates_from_repo(repo, _provider_id := None or repo._connection.execute(
        "SELECT id FROM providers WHERE slug='arvan'").fetchone()["id"], mapping)
    changed = 0
    for row in repo.latest_observations(service_type="vm"):
        region = row["region"] or ""
        if not is_iranian_region(region):
            status, detail = "review", "non-Iranian region; not verified against Iranian rates"
        else:
            tier_rates = lookup.rates_for(row["plan_name"]) if lookup else None
            if tier_rates is None or row["vcpu"] is None:
                status, detail = "review", "no rate-mapping family for this plan"
            else:
                status, detail = verify_bundle(
                    row["plan_name"], row["vcpu"],
                    Decimal(str(row["ram_gb"])), Decimal(str(row["disk_gb"])),
                    Decimal(row["price_in_toman"]), tier_rates, mapping,
                )
        repo.set_rate_verification(row["id"], status, detail)
        changed += 1
    print(f"recomputed verification for {changed} latest observations")
finally:
    repo.close()
