"""Tests for Object Storage row normalization (LLM output -> validated rows)."""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractors.os_schema import LLMStoragePlanRow  # noqa: E402
from normalization.os_validate import normalize_os_row  # noqa: E402


def test_priced_plan_with_tb_capacities():
    row = normalize_os_row(LLMStoragePlanRow(
        plan_name="حرفه‌ای", price_raw="۱۸٬۰۰۰٬۰۰۰ تومان", currency_raw="تومان",
        billing_period_raw="ماهانه", storage_raw="۵ ترابایت", traffic_raw="۲۰ ترابایت",
        requests_raw="۵۰٬۰۰۰", evidence="e",
    ))
    assert row.plan_status == "priced"
    assert row.price_in_toman == Decimal(18000000)
    assert row.storage_included_gb == Decimal(5120)
    assert row.traffic_included_gb == Decimal(20480)
    assert row.requests_included == 50000
    assert row.validation_status == "valid"


def test_free_plan_zero_price_is_a_source_claim():
    row = normalize_os_row(LLMStoragePlanRow(
        plan_name="پایه", price_raw="رایگان", storage_raw="۵ گیگابایت",
        traffic_raw="۲۰ گیگابایت", requests_raw="۱۰٬۰۰۰", evidence="e",
    ))
    assert row.plan_status == "free"
    assert row.price_value == Decimal(0) and row.price_in_toman == Decimal(0)
    assert row.validation_status == "valid"


def test_quote_only_plan_has_no_price():
    row = normalize_os_row(LLMStoragePlanRow(
        plan_name="سازمانی", price_raw="ثبت درخواست",
        unlimited_raw="فضای ذخیره‌سازی نامحدود ترافیک مصرفی نامحدود تعداد درخواست‌های نامحدود",
        evidence="e",
    ))
    assert row.plan_status == "quote_only"
    assert row.price_value is None and row.price_in_toman is None
    assert row.storage_unlimited and row.traffic_unlimited and row.requests_unlimited
    assert row.validation_status == "valid"


def test_unlimited_inside_capacity_text_sets_flag():
    row = normalize_os_row(LLMStoragePlanRow(
        plan_name="x", price_raw="۱ تومان", currency_raw="تومان",
        billing_period_raw="ماهانه", storage_raw="نامحدود", traffic_raw="۱ گیگابایت",
        evidence="e",
    ))
    assert row.storage_unlimited is True
    assert row.storage_included_gb is None
    assert row.validation_status == "valid"


def test_unparsable_price_is_suspect_not_dropped():
    row = normalize_os_row(LLMStoragePlanRow(
        plan_name="x", price_raw="مذاکره می‌شود", storage_raw="۱ گیگابایت",
        traffic_raw="۱ گیگابایت", evidence="e",
    ))
    assert row.validation_status == "suspect"
    assert any("price unparsable" in issue for issue in row.validation_issues)


def test_missing_capacities_flagged_for_priced_plan():
    row = normalize_os_row(LLMStoragePlanRow(
        plan_name="x", price_raw="۱ تومان", currency_raw="تومان",
        billing_period_raw="ماهانه", evidence="e",
    ))
    assert row.validation_status == "suspect"
    assert any("no capacity information" in issue for issue in row.validation_issues)


def test_missing_capacities_ok_for_quote_only():
    row = normalize_os_row(LLMStoragePlanRow(
        plan_name="x", price_raw="تماس بگیرید", evidence="e",
    ))
    assert row.plan_status == "quote_only"
    assert row.validation_status == "valid"
