"""Dashboard tests for the Object Storage view (/object-storage).

Seeds a real database through the repository API (no LLM), then asserts the
scenario comparison table, basis badges and the PAYG rate tables. Arvan's
marketing FAQ is not collected: the rate table is the only tariff basis.
"""

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402
from collectors.arvan_os_rates import parse_os_rates  # noqa: E402
from collectors.hamravesh_os import parse_hamravesh_os_plans  # noqa: E402
from collectors.kubit_os import parse_kubit_os_rates  # noqa: E402
from extractors.os_schema import LLMStoragePlanRow  # noqa: E402
from normalization.os_validate import normalize_os_row  # noqa: E402
from storage.repository import Repository  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "object_storage"


def fa(n):
    return f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


@pytest.fixture(scope="module")
def os_client(tmp_path_factory):
    db = tmp_path_factory.mktemp("osdash") / "os.db"
    repo = Repository(db)
    _seed(repo)
    repo.close()
    app = create_app(db)
    with TestClient(app) as test_client:
        yield test_client


def _seed(repo: Repository) -> None:
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    hamravesh = repo.ensure_provider("hamravesh", "Hamravesh", "https://hamravesh.com/")
    kubit = repo.ensure_provider("kubit", "Kubit", "https://kubit.cloud/")
    parspack = repo.ensure_provider("parspack", "ParsPack", "https://parspack.com/")

    # Hamravesh: parsed deterministically from the captured matrix fixture
    html = (FIXTURES / "hamravesh_os_matrix.html").read_text(encoding="utf-8")
    run = repo.start_run(repo.ensure_source(
        hamravesh, "object_storage", "https://hamravesh.com/pricing?service=object_storage", "playwright"
    ))
    repo.finish_run(run, "success")
    from collectors.pipeline import _overage_toman

    for plan in parse_hamravesh_os_plans(html):
        raw = LLMStoragePlanRow(
            plan_name=plan.plan_name, price_raw=plan.price_raw,
            currency_raw="تومان" if "تومان" in plan.price_raw else "",
            billing_period_raw="ماهانه" if "ثبت درخواست" not in plan.price_raw else "",
            storage_raw=plan.storage_raw, traffic_raw=plan.traffic_raw,
            evidence=plan.evidence,
        )
        normalized = normalize_os_row(raw)
        offering = repo.ensure_offering(
            hamravesh, "object_storage", plan.plan_name,
            product_family="fixed_bundle", provider_tier_raw="", region="",
        )
        repo.record_os_observation(
            run, offering, normalized,
            price_raw=plan.price_raw, currency_raw=raw.currency_raw,
            billing_period_raw=raw.billing_period_raw, evidence=plan.evidence,
            overage_storage_toman_gb=_overage_toman(plan.overage_storage_raw),
            overage_traffic_toman_gb=_overage_toman(plan.overage_traffic_raw),
        )

    # Arvan: PAYG rate table from fixture; plans recorded directly
    run = repo.start_run(repo.ensure_source(
        arvan, "object_storage", "https://www.arvancloud.ir/fa/pricing/cloud-storage", "playwright"
    ))
    repo.finish_run(run, "success")
    rates_html = (FIXTURES / "arvan_os_payg.html").read_text(encoding="utf-8")
    repo.record_os_rates(run, arvan, parse_os_rates(rates_html))

    arvan_plans = [
        ("پایه", "رایگان", "۵ گیگابایت", "۲۰ گیگابایت", None, "۱۰٬۰۰۰"),
        ("رشد", "۱٬۸۰۰٬۰۰۰ تومان", "۵۰۰ گیگابایت", "۲ ترابایت", None, "۲۰٬۰۰۰"),
        ("حرفه‌ای", "۱۸٬۰۰۰٬۰۰۰ تومان", "۵ ترابایت", "۲۰ ترابایت", None, "۵۰٬۰۰۰"),
        ("سازمانی", "ثبت درخواست", None, None,
         "فضای ذخیره‌سازی نامحدود ترافیک مصرفی نامحدود", None),
    ]
    for name, price_raw, storage_raw, traffic_raw, unlimited_raw, requests_raw in arvan_plans:
        raw = LLMStoragePlanRow(
            plan_name=name, price_raw=price_raw,
            currency_raw="تومان" if "تومان" in price_raw else "",
            billing_period_raw="ماهانه" if "تومان" in price_raw else "",
            storage_raw=storage_raw, traffic_raw=traffic_raw,
            unlimited_raw=unlimited_raw, requests_raw=requests_raw, evidence="e",
        )
        normalized = normalize_os_row(raw)
        offering = repo.ensure_offering(
            arvan, "object_storage", name,
            product_family="fixed_bundle", provider_tier_raw="", region="",
        )
        repo.record_os_observation(
            run, offering, normalized,
            price_raw=price_raw, currency_raw=raw.currency_raw,
            billing_period_raw=raw.billing_period_raw, evidence="e",
        )

    # Kubit: free base plan (zero quotas) recorded; the negotiable plan is
    # suspect (توافقی/قابل مذاکره) and stays out, mirroring the pipeline.
    run = repo.start_run(repo.ensure_source(
        kubit, "object_storage", "https://kubit.cloud/fa/pricing/", "http"
    ))
    repo.finish_run(run, "success")
    kubit_html = (FIXTURES / "kubit_pricing.html").read_text(encoding="utf-8")
    repo.record_os_rates(run, kubit, parse_kubit_os_rates(kubit_html))
    from collectors.kubit_os import parse_kubit_os_plans

    for plan in parse_kubit_os_plans(kubit_html):
        raw = LLMStoragePlanRow(
            plan_name=plan.plan_name, price_raw=plan.price_raw,
            currency_raw="تومان" if "تومان" in plan.price_raw else "",
            billing_period_raw="ماهانه" if "رایگان" in plan.price_raw else "",
            storage_raw=plan.storage_raw, traffic_raw=plan.traffic_raw,
            evidence=plan.evidence,
        )
        normalized = normalize_os_row(raw)
        if normalized.validation_status != "valid":
            continue  # suspect rows go to review, never into observations
        offering = repo.ensure_offering(
            kubit, "object_storage", normalized.plan_name,
            product_family="fixed_bundle", provider_tier_raw="", region="",
        )
        repo.record_os_observation(
            run, offering, normalized,
            price_raw=plan.price_raw, currency_raw=raw.currency_raw,
            billing_period_raw=raw.billing_period_raw, evidence=plan.evidence,
        )

    # ParsPack: storage-only calculator quotes (HDD/ایران/۱ ماهه) actually
    # read from the live calculator on 2026-11-16 — no traffic allowance.
    run = repo.start_run(repo.ensure_source(
        parspack, "object_storage", "https://parspack.com/cloud-storage", "playwright"
    ))
    repo.finish_run(run, "success")
    parspack_quotes = [
        (100, "200,000"), (500, "1,000,000"), (5000, "8,500,000"),
        (40000, "68,000,000"), (100000, "170,000,000"),
    ]
    for gb, price in parspack_quotes:
        raw = LLMStoragePlanRow(
            plan_name=f"فضای ابری HDD {fa(gb)} گیگابایت",
            price_raw=f"{fa(int(price.replace(',', '')))} تومان",
            currency_raw="تومان", billing_period_raw="ماهانه",
            storage_raw=f"{fa(gb)} گیگابایت", traffic_raw=None,
            evidence="ماشین‌حساب پارس‌پک (HDD، ایران، ۱ ماهه)",
        )
        normalized = normalize_os_row(raw)
        offering = repo.ensure_offering(
            parspack, "object_storage", normalized.plan_name,
            product_family="calculator_quote", provider_tier_raw="hdd", region="iran",
        )
        repo.record_os_observation(
            run, offering, normalized,
            price_raw=raw.price_raw, currency_raw=raw.currency_raw,
            billing_period_raw=raw.billing_period_raw, evidence=raw.evidence,
        )


def test_os_page_renders_scenarios(os_client):
    text = os_client.get("/object-storage").text
    assert "آبجکت استورج" in text
    assert "مقایسه قیمت" in text
    assert "مقایسه قابلیت‌ها" in text
    assert "مقایسه عملکرد" in text
    for label in ("پایه", "رشد", "حرفه‌ای", "اختصاصی"):
        assert label in text


def test_os_scenario_prices_and_bases(os_client):
    """Hamravesh is the baseline; Arvan matches two bundles exactly and is
    calculated from PAYG rates for the other two sizes; Kubit is calculated
    from its PAYG rates everywhere; ParsPack quotes storage only."""
    client = os_client
    text = "".join(client.get("/object-storage?scenario=" + key).text for key in ("base", "growth", "pro", "dedicated"))
    # baseline (Hamravesh) published prices
    assert fa(375000) in text     # پایه
    assert fa(1500000) in text    # رشد
    assert fa(12500000) in text   # حرفه‌ای
    assert fa(120000000) in text  # اختصاصی
    # Arvan exact-bundle matches (published)
    assert fa(1800000) in text
    assert fa(18000000) in text
    # Arvan calculated scenario for پایه (100GB/400GB): 5GB free storage,
    # 95GB×3,600 + 20GB free traffic, 380GB×965 = 708,700
    assert fa(708700) in text
    # Arvan calculated scenario for اختصاصی (50TB/200TB)
    assert fa(330305100) in text
    # Kubit calculated from its PAYG rates (storage first tier + egress
    # خروج از موقعیت at 750/GB): 570,000 / 2,886,000 / 29,184,000 / 279,552,000
    assert fa(570000) in text
    assert fa(2886000) in text
    assert fa(29184000) in text
    assert fa(279552000) in text
    # ParsPack storage-only quotes: exact at پایه/رشد, nearest-larger above
    assert fa(200000) in text
    assert fa(1000000) in text
    # basis badges present, including the nearest-larger approximation
    assert "محاسبه\u200cشده" in text and "منتشرشده" in text
    assert "تقریبی" in text


def test_os_page_has_no_faq_divergence_banner(os_client):
    """The marketing FAQ is not collected; the rate table is authoritative."""
    text = os_client.get("/object-storage").text
    assert "ناهمخوان" not in text
    assert "پرسش‌های رایج" not in text


def test_os_provider_plan_tables(os_client):
    text = os_client.get("/object-storage").text
    assert "پلن‌های منتشرشده — Hamravesh" in text
    assert "پلن‌های منتشرشده — ArvanCloud" in text
    assert "پلن‌های منتشرشده — Kubit" in text
    assert "پلن‌های منتشرشده — ParsPack" in text
    assert "رایگان" in text          # Arvan/Kubit free plans shown as source claims
    assert "با استعلام قیمت" in text  # quote-only plans visible, not zero


def test_os_provider_tables_are_collapsed_by_default(os_client):
    """Per-provider plan tables and PAYG rates live in closed <details>
    collapsibles so the page opens with just the scenario comparison."""
    import re

    text = os_client.get("/object-storage").text
    details_blocks = re.findall(r"<details\b[^>]*>(.*?)</details>", text, re.DOTALL)
    assert len(details_blocks) == 5  # four provider tables + one PAYG rates block
    # no details element carries the 'open' attribute
    for attrs in re.findall(r"<details\b([^>]*)>", text):
        assert "open" not in attrs.split()
    # the main scenario table must not be inside a collapsible
    all_details_text = " ".join(details_blocks)
    assert "مقایسه سناریوها" not in all_details_text


def test_os_rate_tables_render(os_client):
    text = os_client.get("/object-storage").text
    assert "نرخ‌های مصرف مازاد" in text
    assert "۳٬۶۰۰" in text   # Arvan storage tier (per GB)
    assert "۹۶۵" in text     # Arvan traffic tier (per GB)
    assert "۶٬۸۴۰" in text   # Arvan write requests (per 10k)
    assert "۲٬۷۰۰" in text   # Kubit first storage tier (per GB)
    assert "۷۵۰" in text     # Kubit egress outside the location (per GB)


def test_os_layout_convention_chart_before_primary_table(os_client):
    """Shared layout convention (same as the VM page): the chart card comes
    before the primary comparison table, and exactly one chart card exists."""
    text = os_client.get("/object-storage").text
    assert text.count('class="card chart-card') == 1
    chart_pos = text.find('class="card chart-card')
    table_pos = text.find('class="card table-card"')
    assert 0 < chart_pos < table_pos


def test_os_chart_follows_selected_scenario(os_client):
    from bs4 import BeautifulSoup
    base = os_client.get('/object-storage').text
    pro = os_client.get('/object-storage?scenario=pro').text
    assert os_client.get('/object-storage?scenario=invalid').text == base
    for text in (base, pro):
        soup = BeautifulSoup(text, 'html.parser')
        chart = soup.select_one('.chart-card')
        assert len(soup.select('.chart-card')) == 1
        assert len(chart.select('.bar-provider')) == 4
        assert not chart.select('.chart-group, .swatch')
        assert chart.select('.bar-calculated')
        assert len(chart.select('[style="width: 100%"]')) == 1
        prices = [int(''.join(c for c in el.get_text() if c.isdigit())) for el in chart.select('.bar-price')]
        assert prices == sorted(prices)
        assert len(soup.select('.table-card')[0].select('tbody tr')) == 4
    assert 'bar-approximate' in BeautifulSoup(pro, 'html.parser').select_one('.chart-card').decode()
    assert BeautifulSoup(base, 'html.parser').select_one('.chart-card').decode() != BeautifulSoup(pro, 'html.parser').select_one('.chart-card').decode()


def test_nav_links_to_object_storage(os_client):
    text = os_client.get("/vm").text
    assert '/object-storage' in text
