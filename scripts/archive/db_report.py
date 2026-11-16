"""Read-only report of the current database state (no writes, no API calls)."""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage.repository import Repository  # noqa: E402
from util.jalali import format_jalali  # noqa: E402

DB = ROOT / "data" / "cloud_intel.db"

repo = Repository(DB)
try:
    latest = repo.latest_observations(service_type="vm")
    print(f"Latest valid observations: {len(latest)}")
    by_tier: dict[str, list] = {}
    for row in latest:
        by_tier.setdefault(row["provider_tier_raw"], []).append(row)
    for tier, rows in sorted(by_tier.items()):
        print(f"\n-- tier: {tier} ({len(rows)} plans) --")
        for r in sorted(rows, key=lambda x: (x["region"], x["plan_name"])):
            print(
                f"  {r['plan_name']:15} {str(r['vcpu'])} vCPU {r['ram_gb']:>4} GB RAM "
                f"{r['disk_gb']:>5} GB disk | {r['price_in_toman']:>9} Toman/mo | {r['region']}"
            )

    print("\n-- collection runs --")
    for run in repo._connection.execute(
        "SELECT id, status, started_at, finished_at, prompt_tokens, completion_tokens, "
        "content_hash, model FROM collection_runs ORDER BY id"
    ).fetchall():
        started = format_jalali(run["started_at"])
        finished = format_jalali(run["finished_at"]) if run["finished_at"] else "-"
        print(
            f"  #{run['id']} {run['status']:8} {started} -> {finished} "
            f"tokens={run['prompt_tokens']}/{run['completion_tokens']} "
            f"hash={run['content_hash'][:12] if run['content_hash'] else '-'} model={run['model']}"
        )

    total = repo._connection.execute("SELECT COUNT(*) c FROM price_observations").fetchone()["c"]
    print(f"\nTotal price_observations rows: {total}")
finally:
    repo.close()

evidence = ROOT / "evidence" / "arvan" / "vm"
if evidence.exists():
    print(f"\n-- evidence dirs --")
    for d in sorted(evidence.iterdir()):
        files = [f.name for f in d.iterdir()]
        print(f"  {d.name}: {files}")
