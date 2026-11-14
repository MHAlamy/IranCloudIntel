"""End-to-end mocked pipeline: panel fixture -> LLM rows (mocked) -> normalized
rows compared against manually verified expectations."""

import json
from decimal import Decimal
from pathlib import Path

from extractors.schema import LLMPlanRow
from normalization.validate import normalize_llm_row

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arvan_cloud_server"


def test_full_pipeline_matches_expected_rows():
    panel_html = (FIXTURES / "panel_basic.html").read_text(encoding="utf-8")
    llm_rows = json.loads((FIXTURES / "llm_rows_basic.json").read_text(encoding="utf-8"))["rows"]
    expected = json.loads((FIXTURES / "expected_basic_rows.json").read_text(encoding="utf-8"))["rows"]

    # Simulate the pipeline: rows as the LLM would return them (already mocked),
    # then deterministic normalization.
    assert len(llm_rows) == 8
    plan_urls = {r.plan_name: r.plan_url for r in _parsed_rows(panel_html)}
    normalized = [
        normalize_llm_row(LLMPlanRow(**row), plan_url=plan_urls.get(row["plan_name"]))
        for row in llm_rows
    ]

    assert len(normalized) == len(expected)
    for got, exp in zip(normalized, expected):
        assert got.plan_name == exp["plan_name"]
        assert got.provider_tier_raw == exp["provider_tier_raw"]
        assert got.region == exp["region"]
        assert got.vcpu == exp["vcpu"]
        assert float(got.ram_gb) == exp["ram_gb"]
        assert float(got.disk_gb) == exp["disk_gb"]
        assert got.price_value == Decimal(exp["price_value"])
        assert got.currency == exp["currency"]
        assert got.billing_period == exp["billing_period"]
        assert got.validation_status == exp["validation_status"]
        assert got.price_in_toman == Decimal(exp["price_value"])  # already Toman
        assert got.plan_url and f"size={got.plan_name}" in got.plan_url


def test_validation_flags_unknown_currency_and_missing_resources():
    panel_html = (FIXTURES / "panel_basic.html").read_text(encoding="utf-8")
    _ = panel_html  # pipeline context; the row below is synthetic
    bad = LLMPlanRow(
        plan_name="mystery",
        provider_tier_raw="basic",
        region=None,
        vcpu=None,
        ram_gb=None,
        disk_gb=None,
        disk_type=None,
        price_raw="۱۰۰",
        currency_raw="دلار",
        billing_period_raw="نامشخص",
        evidence="mystery row",
    )
    result = normalize_llm_row(bad)
    assert result.validation_status == "suspect"
    assert result.currency == "unknown"
    assert result.price_in_toman is None  # unknown currency must not become 0
    assert result.billing_period == "unknown"
    assert any("currency" in i for i in result.validation_issues)
    assert any("missing resource" in i for i in result.validation_issues)


def _parsed_rows(panel_html: str):
    from collectors.arvan_clean import parse_plan_rows

    return parse_plan_rows(panel_html)
