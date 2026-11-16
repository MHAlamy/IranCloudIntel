"""Generate a committed test fixture from the latest Arvan snapshot.

Extracts the 'basic' panel (with its pricing table) into
tests/fixtures/arvan_cloud_server/panel_basic.html and prints the parsed rows
so they can be manually checked against the source before writing expected
values.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collectors.arvan_clean import extract_panel_html, parse_plan_rows  # noqa: E402

SOURCE_URL = "https://www.arvancloud.ir/fa/pricing/cloud-server"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "arvan_cloud_server"
EVIDENCE = ROOT / "evidence" / "arvan" / "cloud-server"


def main() -> None:
    snapshots = sorted(EVIDENCE.glob("*_*_tab_economy.html"))
    snapshot = snapshots[-1]
    print(f"Using snapshot: {snapshot.name}")

    panel_html = extract_panel_html(snapshot.read_text(encoding="utf-8"), "basic")
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    fixture_path = FIXTURE_DIR / "panel_basic.html"
    fixture_path.write_text(panel_html, encoding="utf-8")
    print(f"Fixture written: {fixture_path.relative_to(ROOT)} ({len(panel_html):,} chars)")

    rows = parse_plan_rows(panel_html)
    print(f"\nParsed {len(rows)} rows:")
    for r in rows:
        print(
            f"  {r.plan_name:14} cpu={r.cpu_raw:6} ram={r.ram_raw:5} disk={r.disk_raw:6} "
            f"price={r.price_raw:10} {r.currency_raw} region={r.region} url={'yes' if r.plan_url else 'no'}"
        )

    # Regions across rows (needed for the expected fixture)
    regions = sorted({r.region for r in rows})
    print(f"\nDistinct regions: {regions}")

    # Machine-readable dump for building the expected fixture (verified by hand)
    dump = [
        {
            "plan_name": r.plan_name,
            "cpu_raw": r.cpu_raw,
            "ram_raw": r.ram_raw,
            "disk_raw": r.disk_raw,
            "price_raw": r.price_raw,
            "currency_raw": r.currency_raw,
            "region": r.region,
        }
        for r in rows
    ]
    dump_path = FIXTURE_DIR / "parsed_rows_dump.json"
    dump_path.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Row dump written: {dump_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
