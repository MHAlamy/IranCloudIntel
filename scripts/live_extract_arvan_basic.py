"""One bounded live extraction test against the Arvan basic-tab fixture.

Milestone 2 exit check: feed the cleaned markdown (built deterministically
from the real page snapshot) to the configured LLM, normalize the returned
rows deterministically, and compare against the hand-verified expected rows.

Billable: a single chat completion (approved by the owner). Saves full
telemetry and output under evidence/ for audit.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from collectors.arvan_clean import build_cleaned_markdown, parse_plan_rows, sha256_text  # noqa: E402
from extractors.llm import LLMClient, LLMError  # noqa: E402
from extractors.prompts import build_extraction_messages  # noqa: E402
from extractors.schema import LLMPlanRow  # noqa: E402
from normalization.validate import normalize_llm_row  # noqa: E402

SOURCE_URL = "https://www.arvancloud.ir/fa/pricing/cloud-server"
FIXTURES = ROOT / "tests" / "fixtures" / "arvan_cloud_server"
EVIDENCE = ROOT / "evidence" / "arvan" / "cloud-server"
MAX_TOKENS = 8000


def main() -> int:
    panel_html = (FIXTURES / "panel_basic.html").read_text(encoding="utf-8")
    rows = parse_plan_rows(panel_html)
    cleaned = build_cleaned_markdown("basic", rows, SOURCE_URL)
    content_hash = sha256_text(cleaned)
    print(f"Cleaned content: {len(cleaned)} chars, sha256 {content_hash[:16]}…")
    print(f"Source rows in cleaned content: {len(rows)}")

    messages = build_extraction_messages(
        cleaned,
        context={
            "provider": "ArvanCloud",
            "service": "vm",
            "tab": "basic",
            "source_url": SOURCE_URL,
            "currency_note": "Prices are shown in Toman with Persian digits.",
        },
    )

    with LLMClient() as client:
        try:
            llm_rows, telemetry = client.extract_rows(messages, max_tokens=MAX_TOKENS)
        except LLMError as exc:
            print(f"LIVE TEST FAILED: {exc}")
            return 1

    print(
        f"\nTelemetry: model={telemetry.model} finish={telemetry.finish_reason} "
        f"prompt={telemetry.prompt_tokens} completion={telemetry.completion_tokens} "
        f"(reasoning={telemetry.reasoning_tokens}) total={telemetry.total_tokens}"
    )

    # Deterministic validation of whatever the model returned
    parsed_ok, rejected = [], []
    for raw in llm_rows:
        try:
            parsed_ok.append((raw, normalize_llm_row(LLMPlanRow(**raw))))
        except Exception as exc:  # schema violations are recorded, not swallowed
            rejected.append((raw, str(exc)))

    print(f"\nModel returned {len(llm_rows)} rows: {len(parsed_ok)} schema-valid, {len(rejected)} rejected")
    for raw, err in rejected:
        print(f"  REJECTED {raw.get('plan_name', '?')}: {err[:140]}")

    # Compare against hand-verified expectations
    expected = json.loads((FIXTURES / "expected_basic_rows.json").read_text(encoding="utf-8"))["rows"]
    by_name = {n.plan_name: n for _, n in parsed_ok}
    matches, mismatches = 0, 0
    print("\nRow-by-row comparison (normalized vs hand-verified expectation):")
    for exp in expected:
        got = by_name.get(exp["plan_name"])
        if got is None:
            print(f"  MISSING {exp['plan_name']}")
            mismatches += 1
            continue
        checks = {
            "vcpu": got.vcpu == exp["vcpu"],
            "ram": float(got.ram_gb) == exp["ram_gb"],
            "disk": float(got.disk_gb) == exp["disk_gb"],
            "price": str(got.price_value) == exp["price_value"],
            "currency": got.currency == exp["currency"],
            "billing": got.billing_period == exp["billing_period"],
            "region": got.region == exp["region"],
            "status": got.validation_status == exp["validation_status"],
        }
        if all(checks.values()):
            matches += 1
            print(f"  OK      {exp['plan_name']}: price={got.price_value} {got.currency}/mo region={got.region}")
        else:
            mismatches += 1
            failed = [k for k, ok in checks.items() if not ok]
            print(f"  MISMATCH {exp['plan_name']}: fields {failed} -> {got.model_dump()}")
    extra = set(by_name) - {e["plan_name"] for e in expected}
    if extra:
        mismatches += len(extra)
        print(f"  UNEXPECTED EXTRA ROWS: {sorted(extra)}")

    verdict = "PASS" if matches == len(expected) and mismatches == 0 else "FAIL"
    print(f"\nLIVE TEST VERDICT: {verdict} ({matches}/{len(expected)} rows fully matched)")

    # Save evidence for audit
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = {
        "observed_at": stamp,
        "source_url": SOURCE_URL,
        "cleaned_content_sha256": content_hash,
        "model": telemetry.model,
        "usage": {
            "prompt_tokens": telemetry.prompt_tokens,
            "completion_tokens": telemetry.completion_tokens,
            "reasoning_tokens": telemetry.reasoning_tokens,
            "total_tokens": telemetry.total_tokens,
        },
        "llm_rows_raw": llm_rows,
        "rejected": [{"row": r, "error": e} for r, e in rejected],
        "verdict": verdict,
        "matches": matches,
        "expected_count": len(expected),
    }
    out_path = EVIDENCE / f"{stamp}_live_extract_basic.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Evidence saved: {out_path.name}")
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
