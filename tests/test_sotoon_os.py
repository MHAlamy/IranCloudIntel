"""Sotoon HiCap Object Storage: offline rates, scenario pricing and dashboard."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.os_view import OS_RATE_FILTERS, _rates_scenario_price, build_os_view
from collectors.offline_pipeline import run_offline_rates_collection
from collectors.sotoon_offline import build_os_collection, collect_sotoon_os_offline
from config.loader import load_benchmarks, load_providers
from storage.repository import Repository

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "datasets" / "offline" / "sotoon-price-1405-v3"

# Neda HiCap: 39,000 IRR/GB-month, egress 27,000 → 10,500 IRR/GB,
# requests 1,100 IRR per 1,000.
EXPECTED_TOTALS = {
    "base": Decimal("1411000"),
    "growth": Decimal("6615800"),
    "pro": Decimal("61371200"),
    "dedicated": Decimal("558553200"),
}

# Same scenarios, but 80% of egress is served through Sotoon's CDN and is not
# billed as Object Storage traffic (only the remaining 20% is charged).
EXPECTED_CDN_TOTALS = {
    "base": Decimal("611000"),
    "growth": Decimal("3039000"),
    "pro": Decimal("29429600"),
    "dedicated": Decimal("282897200"),
}


def sotoon_config():
    provider = next(p for p in load_providers().providers if p.slug == "sotoon")
    source = next(s for s in provider.sources if s.service_type == "object_storage")
    return provider, source


def rate_dicts(collection) -> list[dict]:
    return [
        {
            "category": r.category, "tier_label": r.tier_label,
            "range_label": r.range_label, "range_min_gb": r.range_min_gb,
            "range_max_gb": r.range_max_gb, "amount_toman": r.amount_toman,
            "is_free": r.is_free, "unit": r.unit,
        }
        for r in collection.rates
    ]


def test_hicap_rates_cover_capacity_egress_and_requests():
    collection = build_os_collection(
        PACKAGE, region="Neda", storage_class="HiCap", tb_to_gb=1024
    )
    assert collection.valid_until == "2027-03-20"
    by_category = {}
    for rate in collection.rates:
        by_category.setdefault(rate.category, []).append(rate)

    assert len(by_category["storage"]) == 1
    assert by_category["storage"][0].amount_toman == "3900"
    assert by_category["storage"][0].tier_label == "HiCap"

    egress = by_category["traffic"]
    assert [r.amount_toman for r in egress] == [
        "2700", "2500", "2300", "2100", "1950", "1800", "1600", "1350", "1050",
    ]
    assert egress[0].range_min_gb == "0" and egress[0].range_max_gb == "50"
    # successive tiers must be contiguous for the tariff arithmetic
    for previous, current in zip(egress, egress[1:]):
        assert current.range_min_gb == previous.range_max_gb
    assert egress[-1].range_max_gb is None
    assert "p.7" in egress[0].evidence

    requests = by_category["requests"]
    assert len(requests) == 1
    assert requests[0].amount_toman == "110"
    assert requests[0].unit == "هر ۱۰۰۰ درخواست"
    assert "p.6" in requests[0].evidence


@pytest.mark.parametrize("scenario_key,expected", EXPECTED_TOTALS.items())
def test_scenario_price_includes_estimated_requests(scenario_key, expected):
    benchmarks = load_benchmarks().object_storage
    scenario = benchmarks.scenarios[scenario_key]
    collection = build_os_collection(
        PACKAGE, region="Neda", storage_class="HiCap", tb_to_gb=benchmarks.tb_to_gb
    )
    price, notes = _rates_scenario_price(
        rate_dicts(collection),
        Decimal(str(scenario.storage_gb)),
        Decimal(str(scenario.traffic_gb)),
        scenario.requests,
        OS_RATE_FILTERS["sotoon"],
    )
    assert price == expected
    assert any("درخواست برآوردی" in note for note in notes)


def test_request_estimate_is_a_low_end_share_of_the_total():
    """The request charge must stay modest relative to storage+traffic."""
    benchmarks = load_benchmarks().object_storage
    scenario = benchmarks.scenarios["base"]
    collection = build_os_collection(
        PACKAGE, region="Neda", storage_class="HiCap", tb_to_gb=benchmarks.tb_to_gb
    )
    rates = rate_dicts(collection)
    with_requests, _ = _rates_scenario_price(
        rates, Decimal("100"), Decimal("400"), scenario.requests, OS_RATE_FILTERS["sotoon"]
    )
    without_requests, _ = _rates_scenario_price(
        rates, Decimal("100"), Decimal("400"), 0, OS_RATE_FILTERS["sotoon"]
    )
    request_cost = with_requests - without_requests
    assert request_cost == Decimal("11000")  # 100,000 / 1,000 × 110
    assert request_cost < with_requests / 100


def test_missing_request_rate_is_not_treated_as_zero():
    collection = build_os_collection(
        PACKAGE, region="Neda", storage_class="HiCap", tb_to_gb=1024
    )
    rates = [r for r in rate_dicts(collection) if r["category"] != "requests"]
    price, notes = _rates_scenario_price(
        rates, Decimal("100"), Decimal("400"), 100000, OS_RATE_FILTERS["sotoon"]
    )
    assert price is None
    assert any("یافت نشد" in note for note in notes)


@pytest.fixture
def imported_os(tmp_path):
    db = tmp_path / "sotoon_os.db"
    repo = Repository(db)
    provider, source = sotoon_config()
    outcome = run_offline_rates_collection(
        provider, source, repo, collect_sotoon_os_offline,
        evidence_root=tmp_path / "evidence",
    )
    yield repo, outcome, source, db
    repo.close()


def test_import_stores_manual_provenance(imported_os):
    repo, outcome, _, _ = imported_os
    assert outcome.status == "success"
    assert outcome.observations == 11

    provider, _ = sotoon_config()
    from app.view_common import _provider_id

    rates = repo.latest_os_rates(_provider_id(repo, "sotoon"))
    assert len(rates) == 11
    assert {r["collection_method"] for r in rates} == {"manual"}
    assert {r["valid_until"] for r in rates} == {"2027-03-20"}
    assert "Sotoon price list" in rates[0]["source_document"]


def test_second_import_is_skipped_when_unchanged(imported_os, tmp_path):
    repo, _, source, _ = imported_os
    provider, _ = sotoon_config()
    again = run_offline_rates_collection(
        provider, source, repo, collect_sotoon_os_offline,
        evidence_root=tmp_path / "evidence2",
    )
    assert again.status == "success" and again.skipped is True


def test_view_calculates_sotoon_with_requests_and_provenance(imported_os):
    repo, _, _, _ = imported_os
    view = build_os_view(repo, "base")
    row = next(r for r in view["comparison_rows"] if r["provider_name"] == "Sotoon")
    assert row["price"] == EXPECTED_TOTALS["base"]
    assert row["basis"] == "calculated"
    assert row["provenance"] == "manual"
    assert any("منبع دستی" in note for note in row["notes"])
    assert any("۱۰۰٬۰۰۰ درخواست برآوردی" in note for note in row["notes"])
    # the page-level VAT/partial-total caveat moved to the method box; row
    # notes must not repeat it
    assert not any("مالیات" in note for note in row["notes"])
    assert not any("جمع جزئی" in note for note in row["notes"])


@pytest.mark.parametrize("scenario_key", EXPECTED_TOTALS)
def test_cdn_offload_adds_a_second_sotoon_result(imported_os, scenario_key):
    repo, _, _, _ = imported_os
    view = build_os_view(repo, scenario_key)
    sotoon_rows = [r for r in view["comparison_rows"] if r["slug"] == "sotoon"]
    assert [r["provider_name"] for r in sotoon_rows] == ["Sotoon", "Sotoon + CDN"]
    full, cdn = sotoon_rows
    assert full["price"] == EXPECTED_TOTALS[scenario_key]
    assert cdn["price"] == EXPECTED_CDN_TOTALS[scenario_key]
    assert cdn["price"] < full["price"]
    assert cdn["provenance"] == "manual"
    assert cdn["basis"] == "calculated"


def test_both_sotoon_results_explain_the_traffic_assumption(imported_os):
    repo, _, _, _ = imported_os
    view = build_os_view(repo, "base")
    full, cdn = [r for r in view["comparison_rows"] if r["slug"] == "sotoon"]

    assert full["plan_name"] == "پیکربندی معادل (کل ترافیک)"
    assert any("کل ترافیک سناریو" in note and "CDN" in note for note in full["notes"])

    assert "۲۰٪" in cdn["plan_name"]
    assert any("۸۰٪ ترافیک از CDN" in note for note in cdn["notes"])
    assert any("هزینه‌ی خود CDN در این عدد نیست" in note for note in cdn["notes"])
    # the request estimate and provenance apply to both results
    for row in (full, cdn):
        assert any("درخواست برآوردی" in note for note in row["notes"])
        assert any("منبع دستی" in note for note in row["notes"])


def test_scenarios_expose_the_request_estimate(imported_os):
    repo, _, _, _ = imported_os
    view = build_os_view(repo, "growth")
    scenario = view["selected_scenario"]
    assert scenario["requests"] == 500000
    assert scenario["requests_fa"] == "۵۰۰٬۰۰۰"


def test_dashboard_renders_sotoon_with_manual_badge(imported_os):
    _, _, _, db = imported_os
    with TestClient(create_app(db)) as client:
        text = client.get("/object-storage?scenario=base").text
        assert "Sotoon" in text
        assert "Sotoon + CDN" in text
        assert "badge-manual" in text and "دستی" in text
        assert "منبع دستی" in text
        assert "برآورد" in text
        assert "۱۴۰۵/۱۲/۲۹" in text
        assert "۸۰٪ ترافیک از CDN" in text
        # the rate table shows the request unit and the manual provenance
        assert "هر ۱۰۰۰ درخواست" in text
        # the single page-level explanation replaces per-row tax caveats
        assert "نحوه محاسبه قیمت" in text
        assert text.count("مالیات") == 1
