"""Tests for Object Storage deterministic parsers
(Hamravesh matrix, Arvan PAYG, Kubit bucket tables, ParsPack quotes)."""

import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.arvan_os_rates import (  # noqa: E402
    crosscheck_arvan_os_plans,
    parse_gb_bounds,
    parse_os_plan_matrix,
    parse_os_rates,
)
from collectors.hamravesh_os import parse_hamravesh_os_plans  # noqa: E402
from normalization.os_validate import parse_capacity_gb, parse_requests  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "object_storage"


# -- capacity / range parsing -------------------------------------------------

def test_capacity_gb_parses_tb_with_configurable_factor():
    assert parse_capacity_gb("۵۰۰ گیگابایت") == Decimal(500)
    assert parse_capacity_gb("۵ ترابایت") == Decimal(5120)       # 5 × 1024
    assert parse_capacity_gb("۵ TB", tb_to_gb=1000) == Decimal(5000)
    assert parse_capacity_gb("۲۰ ترابایت") == Decimal(20480)
    assert parse_capacity_gb("۱٫۵ ترابایت") == Decimal(1536)     # Persian decimal point


def test_capacity_gb_unlimited_and_unknown_are_none():
    assert parse_capacity_gb(None) is None
    assert parse_capacity_gb("") is None
    assert parse_capacity_gb("نامحدود") is None
    with pytest.raises(ValueError):
        parse_capacity_gb("چند")  # non-empty text without a unit must be flagged


def test_requests_parsing():
    assert parse_requests("۲۰٬۰۰۰") == 20000
    assert parse_requests(None) is None
    assert parse_requests("نامحدود") is None


def test_gb_bounds_parsing():
    assert parse_gb_bounds("تا ۵ گیگابایت") == (Decimal("0"), Decimal(5))
    assert parse_gb_bounds("۵ گیگابایت تا ۵ ترابایت") == (Decimal(5), Decimal(5120))
    assert parse_gb_bounds("۵ تا ۵۰ ترابایت") == (Decimal(5120), Decimal(51200))
    assert parse_gb_bounds("۱٫۵ تا ۳ ترابایت") == (Decimal("1536"), Decimal("3072"))
    assert parse_gb_bounds("بیش از ۵۰۰ ترابایت") == (Decimal(512000), None)
    assert parse_gb_bounds("۲۰۰ ترابایت تا ۲ پتابایت") == (Decimal(204800), Decimal(2097152))
    assert parse_gb_bounds("") == (None, None)


# -- Hamravesh matrix ---------------------------------------------------------

@pytest.fixture(scope="module")
def hamravesh_plans():
    return parse_hamravesh_os_plans((FIXTURES / "hamravesh_os_matrix.html").read_text(encoding="utf-8"))


def test_hamravesh_plans_complete(hamravesh_plans):
    names = [p.plan_name for p in hamravesh_plans]
    assert names == ["پایه", "رشد", "حرفه‌ای", "اختصاصی", "سازمانی"]


def test_hamravesh_prices_and_capacities(hamravesh_plans):
    by_name = {p.plan_name: p for p in hamravesh_plans}
    assert by_name["پایه"].price_raw == "۳۷۵,۰۰۰ تومان"
    assert by_name["پایه"].storage_raw == "۱۰۰ GB"
    assert by_name["پایه"].traffic_raw == "۴۰۰ GB"
    assert by_name["رشد"].price_raw == "۱,۵۰۰,۰۰۰ تومان"
    assert by_name["رشد"].storage_raw == "۵۰۰ GB"
    assert by_name["رشد"].traffic_raw == "۲ TB"
    assert by_name["حرفه‌ای"].traffic_raw == "۲۰ TB"
    assert by_name["اختصاصی"].price_raw == "۱۲۰,۰۰۰,۰۰۰ تومان"
    assert by_name["اختصاصی"].storage_raw == "۵۰ TB"


def test_hamravesh_overage_and_quote_only(hamravesh_plans):
    by_name = {p.plan_name: p for p in hamravesh_plans}
    assert by_name["پایه"].overage_storage_raw == "۳,۰۰۰ تومان"
    assert by_name["پایه"].overage_traffic_raw == "۱,۲۰۰ تومان"
    assert by_name["سازمانی"].price_raw == "ثبت درخواست"
    assert by_name["سازمانی"].storage_raw is None       # page states nothing
    assert by_name["سازمانی"].overage_storage_raw == "تماس بگیرید"


# -- Arvan PAYG rate tables ---------------------------------------------------

@pytest.fixture(scope="module")
def arvan_rates():
    html = (FIXTURES / "arvan_os_payg.html").read_text(encoding="utf-8")
    return parse_os_rates(html)


def test_arvan_storage_tiers(arvan_rates):
    storage = [r for r in arvan_rates if r.category == "storage" and "استاندارد" in r.tier_label]
    amounts = [(r.range_min_gb, r.range_max_gb, r.amount_toman, r.is_free) for r in storage]
    assert amounts == [
        ("0", "5", None, True),
        ("5", "5120", "3600", False),
        ("5120", "51200", "3060", False),
        ("51200", "512000", "2700", False),
        ("512000", None, "2340", False),
    ]


def test_arvan_hiops_tier(arvan_rates):
    hiops = [r for r in arvan_rates if r.category == "storage" and "Hiops" in r.tier_label]
    assert len(hiops) == 1 and hiops[0].amount_toman == "10800"


def test_arvan_request_tiers(arvan_rates):
    reads = [r for r in arvan_rates if r.category == "requests_read"]
    growth = [r for r in reads if r.tier_label == "بسته رشد"]
    amounts = [(r.range_label, r.amount_toman, r.is_free) for r in growth]
    assert amounts == [
        ("تا ۲۰٬۰۰۰ درخواست", None, True),
        ("۲۰٬۰۰۰ تا ۱ میلیون درخواست", "630", False),
        ("۱ میلیون تا ۲۰ میلیون درخواست", "504", False),
        ("۲۰ میلیون تا ۲۰۰ میلیون درخواست", "445", False),
        ("بیش از ۲۰۰ میلیون درخواست", "315", False),
    ]
    writes = [r for r in arvan_rates if r.category == "requests_write" and r.tier_label == "بسته حرفه‌ای"]
    assert [(r.range_label, r.amount_toman) for r in writes] == [
        ("تا ۵۰٬۰۰۰ درخواست", None),
        ("بیش از ۵۰٬۰۰۰ درخواست", "6840"),
    ]


def test_arvan_traffic_tiers(arvan_rates):
    traffic = [r for r in arvan_rates if r.category == "traffic"]
    amounts = [(r.range_min_gb, r.range_max_gb, r.amount_toman, r.is_free) for r in traffic]
    assert amounts == [
        ("0", "20", None, True),
        ("20", "20480", "965", False),
        ("20480", "204800", "820", False),
        ("204800", "2097152", "675", False),
        ("2097152", None, "580", False),
    ]


def test_arvan_feature_rates(arvan_rates):
    features = {r.tier_label: r.amount_toman for r in arvan_rates if r.category == "feature"}
    assert features == {"نقطه دسترسی": "96", "آنتی ویروس": "11250"}


# -- plan matrix + cross-check ------------------------------------------------

def test_arvan_plan_matrix_parsed():
    html = (FIXTURES / "arvan_os_matrix.html").read_text(encoding="utf-8")
    matrix = parse_os_plan_matrix(html)
    assert matrix["storage"] == ["۵ گیگابایت", "۵۰۰ گیگابایت", "۵ ترابایت", "نامحدود"]
    assert matrix["traffic"] == ["۲۰ گیگابایت", "۲ ترابایت", "۲۰ ترابایت", "نامحدود"]
    assert matrix["requests"] == ["۱۰٬۰۰۰", "۲۰٬۰۰۰", "۵۰٬۰۰۰", "۱۰۰٬۰۰۰"]


def test_crosscheck_flags_request_inconsistency():
    """Arvan's own page contradicts itself for سازمانی: the card says unlimited
    requests, the matrix says ۱۰۰٬۰۰۰. The cross-check must surface this."""
    from extractors.os_schema import LLMStoragePlanRow
    from normalization.os_validate import normalize_os_row

    html = (FIXTURES / "arvan_os_matrix.html").read_text(encoding="utf-8")
    raws = [
        LLMStoragePlanRow(plan_name="پایه", price_raw="رایگان", storage_raw="۵ گیگابایت",
                          traffic_raw="۲۰ گیگابایت", requests_raw="۱۰٬۰۰۰", evidence="e"),
        LLMStoragePlanRow(plan_name="رشد", price_raw="۱٬۸۰۰٬۰۰۰ تومان", currency_raw="تومان",
                          billing_period_raw="ماهانه", storage_raw="۵۰۰ گیگابایت",
                          traffic_raw="۲ ترابایت", requests_raw="۲۰٬۰۰۰", evidence="e"),
        LLMStoragePlanRow(plan_name="حرفه‌ای", price_raw="۱۸٬۰۰۰٬۰۰۰ تومان", currency_raw="تومان",
                          billing_period_raw="ماهانه", storage_raw="۵ ترابایت",
                          traffic_raw="۲۰ ترابایت", requests_raw="۵۰٬۰۰۰", evidence="e"),
        LLMStoragePlanRow(plan_name="سازمانی", price_raw="ثبت درخواست",
                          unlimited_raw="فضای ذخیره‌سازی نامحدود ترافیک مصرفی نامحدود تعداد درخواست‌های نامحدود",
                          evidence="e"),
    ]
    pairs = [(raw, normalize_os_row(raw)) for raw in raws]
    entries = crosscheck_arvan_os_plans(html, pairs)
    request_flags = [e for e in entries if e.get("check") == "requests"]
    assert any(e.get("plan") == "سازمانی" for e in request_flags)
    # the three priced plans must cross-check clean on storage/traffic
    assert not [e for e in entries if e.get("check") in ("storage", "traffic")]


# -- Kubit bucket tables -------------------------------------------------------

@pytest.fixture(scope="module")
def kubit_html():
    return (FIXTURES / "kubit_pricing.html").read_text(encoding="utf-8")


def test_kubit_bucket_plans_parsed(kubit_html):
    from collectors.kubit_os import parse_kubit_os_plans

    plans = parse_kubit_os_plans(kubit_html)
    names = [p.plan_name for p in plans]
    assert names == ["پایه", "اختصاصی"]
    by_name = {p.plan_name: p for p in plans}
    # base plan: free with explicitly zero quotas (source claims, valid)
    assert by_name["پایه"].price_raw == "رایگان"
    assert by_name["پایه"].storage_raw == "۰ گیگابایت"
    assert by_name["پایه"].traffic_raw == "۰ گیگابایت"
    # dedicated plan: negotiable capacities (unknown -> None) and quote price
    assert by_name["اختصاصی"].storage_raw is None
    assert by_name["اختصاصی"].traffic_raw is None
    assert by_name["اختصاصی"].price_raw == "توافقی"


def test_kubit_bucket_plans_normalize(kubit_html):
    """The free base plan must normalize valid (zero is a source claim);
    the negotiable plan is intentionally flagged, not silently accepted."""
    from collectors.kubit_os import parse_kubit_os_plans
    from extractors.os_schema import LLMStoragePlanRow
    from normalization.os_validate import normalize_os_row

    for plan in parse_kubit_os_plans(kubit_html):
        raw = LLMStoragePlanRow(
            plan_name=plan.plan_name, price_raw=plan.price_raw,
            currency_raw="تومان" if "تومان" in plan.price_raw else "",
            billing_period_raw="ماهانه" if "رایگان" in plan.price_raw else "",
            storage_raw=plan.storage_raw, traffic_raw=plan.traffic_raw,
            evidence=plan.evidence,
        )
        normalized = normalize_os_row(raw)
        if plan.plan_name == "پایه":
            assert normalized.validation_status == "valid"
            assert normalized.plan_status == "free"
            assert normalized.storage_included_gb == Decimal("0")
        else:
            assert normalized.validation_status == "suspect"


def test_kubit_storage_tiers_chained(kubit_html):
    """'تا X' starts at 0, 'مازاد تا X' continues from the previous tier,
    'بیش از X' runs unbounded — with the configured TB→GB factor."""
    from collectors.kubit_os import parse_kubit_os_rates

    rates = parse_kubit_os_rates(kubit_html)
    storage = [
        (r.range_min_gb, r.range_max_gb, r.amount_toman)
        for r in rates if r.category == "storage"
    ]
    assert storage == [
        ("0", "10240", "2700"),
        ("10240", "102400", "2400"),
        ("102400", "716800", "2000"),
        ("716800", None, "1800"),
    ]


def test_kubit_traffic_and_request_rates(kubit_html):
    from collectors.kubit_os import parse_kubit_os_rates

    rates = parse_kubit_os_rates(kubit_html)
    traffic = {r.tier_label: r.amount_toman for r in rates if r.category == "traffic"}
    assert traffic == {
        "ترافیک خروجی داخل موقعیت": "200",
        "ترافیک خروجی خارج موقعیت": "750",
        "ترافیک ورودی از داخل موقعیت": "400",
        "ترافیک ورودی از خارج موقعیت": "1800",
    }
    reads = [r for r in rates if r.category == "requests_read"]
    assert len(reads) == 1 and reads[0].amount_toman == "250"
    writes = [r for r in rates if r.category == "requests_write"]
    assert len(writes) == 1 and writes[0].amount_toman == "2500"
    files = [r for r in rates if r.category == "feature"]
    assert len(files) == 1 and files[0].amount_toman == "200"


def test_kubit_cleaned_markdown_contains_both_tables(kubit_html):
    from collectors.kubit_os import clean_kubit_os

    cleaned = clean_kubit_os(kubit_html, "https://kubit.cloud/fa/pricing/")
    assert "## پلن‌های باکت" in cleaned
    assert "## مصرف مازاد باکت" in cleaned
    assert "مالیات بر ارزش افزوده" in cleaned


# -- ParsPack storage calculator quotes ----------------------------------------

class _StubPage:
    """Minimal page stand-in for read_quote/collect parsing helpers."""

    def __init__(self, lines: list[str]):
        self._lines = lines

    def inner_text(self, _selector: str) -> str:
        return "\n".join(self._lines)


def test_parspack_quote_reading():
    from collectors.parspack_os import read_quote

    page = _StubPage([
        "جمع کل:", "ماهیانه", "۲۰۰٬۰۰۰", "تومان",
        "۱۰۰ GB",
    ])
    assert read_quote(page) == (100, 200000)


def test_parspack_quote_reading_unreadable_returns_none():
    from collectors.parspack_os import read_quote

    assert read_quote(_StubPage(["قیمت", "تومان"])) is None


def test_parspack_quotes_markdown_is_deterministic():
    from collectors.parspack_os import quotes_markdown

    quotes = [
        {"position": 0, "storage_gb": 1, "monthly_toman": "16000"},
        {"position": 6, "storage_gb": 100, "monthly_toman": "200000"},
    ]
    first = quotes_markdown(quotes, "https://parspack.com/cloud-storage")
    second = quotes_markdown(quotes, "https://parspack.com/cloud-storage")
    assert first == second
    assert "| 6 | 100 | 200000 |" in first
    assert "HDD" in first and "ایران" in first
    assert "ترافیک" in first  # the no-traffic caveat is part of the evidence


def test_parspack_plan_name_persian_format():
    from collectors.parspack_os import _format_fa

    assert _format_fa(100) == "۱۰۰"
    assert _format_fa(100000) == "۱۰۰٬۰۰۰"
