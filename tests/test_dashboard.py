"""Dashboard tests: routes render Persian comparison views from a seeded DB."""

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402
from collectors.arvan_rates import RateRow  # noqa: E402
from extractors.schema import LLMPlanRow, NormalizedPlanRow  # noqa: E402
from storage.repository import Repository  # noqa: E402


@pytest.fixture(scope="module")
def client_tuple(tmp_path_factory):
    db = tmp_path_factory.mktemp("dash") / "dash.db"
    repo = Repository(db)
    _seed(repo)
    g3_offering = repo._connection.execute(
        "SELECT id FROM offerings WHERE plan_name='g3-small1'"
    ).fetchone()["id"]
    repo.close()
    app = create_app(db)
    with TestClient(app) as test_client:
        yield test_client, g3_offering


def _seed(repo: Repository) -> None:
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    source = repo.ensure_source(arvan, "vm", "https://www.arvancloud.ir/fa/pricing/cloud-server", "playwright")

    # rates (subset used by calculated pricing)
    rates = [
        RateRow("cpu", "iran", "هر vCore", "Basic", "252000", ""),
        RateRow("cpu", "iran", "هر vCore", "Standard", "327600", ""),
        RateRow("cpu", "iran", "هر vCore", "Premium", "478800", ""),
        RateRow("ram", "iran", "هر گیگابایت", "Basic", "196200", ""),
        RateRow("ram", "iran", "هر گیگابایت", "Standard", "255060", ""),
        RateRow("ram", "iran", "هر گیگابایت", "Premium", "372780", ""),
        RateRow("storage", "iran", "هر گیگابایت", "بلاک استوریج (Eco)", "18000", ""),
        RateRow("ipv4", "iran", "هر آدرس", "به‌ازای IPv4 اول", "234000", ""),
    ]
    run = repo.start_run(source)
    repo.finish_run(run, "success", model="GPT-5-Mini", prompt_tokens=100, completion_tokens=100)
    repo.record_rates(run, arvan, rates)

    def bundle(plan_name, tier_raw, region, vcpu, ram, disk, price, verification="verified"):
        offering = repo.ensure_offering(arvan, "vm", plan_name, provider_tier_raw=tier_raw, region=region)
        raw = LLMPlanRow(
            plan_name=plan_name, provider_tier_raw=tier_raw, region=region,
            vcpu=vcpu, ram_gb=float(ram), disk_gb=float(disk), disk_type=None,
            price_raw="۱", currency_raw="تومان", billing_period_raw="ماهانه", evidence="e",
        )
        normalized = NormalizedPlanRow(
            plan_name=plan_name, provider_tier_raw=tier_raw, region=region,
            vcpu=vcpu, ram_gb=Decimal(ram), disk_gb=Decimal(disk), disk_type=None,
            price_value=Decimal(price), currency="toman", price_in_toman=Decimal(price),
            billing_period="monthly", pricing_type="fixed_bundle",
            validation_status="valid", validation_issues=[],
        )
        obs_id = repo.record_observation(run, offering, raw, normalized, evidence="e")
        repo.set_rate_verification(obs_id, verification)

    # real verified bundles
    bundle("eco-small2", "basic", "ir-thr-ba1", 1, 2, 25, 1135080)
    bundle("g3-small1", "standard", "ir-thr-ba1", 1, 2, 75, 2421720)
    bundle("c2-medium1", "standard", "ir-thr-ba1", 2, 4, 25, 2359440, verification="mismatch")
    bundle("g6.5-small1", "premium", "ir-thr-ba1", 2, 2, 75, 3287160)
    bundle("c1-medium2", "basic", "eu-west1-a", 4, 8, 75, 5086400)


def test_health(client_tuple):
    client = client_tuple[0]
    assert client.get("/health").json() == {"status": "ok"}


def test_root_redirects_to_vm(client_tuple):
    client = client_tuple[0]
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (301, 302, 307)
    assert response.headers["location"].endswith("/vm")


def test_vm_default_view_is_persian(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm")
    assert response.status_code == 200
    text = response.text
    assert "مقایسه قیمت سرور ابری" in text
    assert "استاندارد" in text  # default tier active
    assert "تومان" in text
    assert "منتشرشده" in text


def test_vm_small_standard_shows_calculated_baseline_only(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm?tier=standard&size=small")
    text = response.text
    # baseline 1/2/20 has no exact bundle (g3-small1 is 1/2/75) -> calculated only
    expected = 234000 + 327600 + 2 * 255060 + 20 * 18000  # 1,431,720
    fa = f"{expected:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert fa in text
    assert "محاسبه\u200cشده" in text
    assert "g3-small1" not in text and "g4-small1" not in text  # near-miss bundles dropped


def test_vm_no_verification_badges_or_region_column(client_tuple):
    client = client_tuple[0]
    text = client.get("/vm").text
    assert "تأیید" not in text  # verification belongs to the plan detail page
    assert "منطقه" not in text  # region column removed; Iran-only noted in header
    assert "تنها برای مناطق ایران" in text


def test_vm_date_only_last_checked(client_tuple):
    client = client_tuple[0]
    text = client.get("/vm").text
    assert "۱۳:۳۰" not in text  # no time-of-day in the table


def test_vm_medium_shows_calculated_price_for_economy(client_tuple):
    client = client_tuple[0]
    # economy has no Medium bundle; rates enable a calculated price
    response = client.get("/vm?tier=economy&size=medium")
    text = response.text
    assert "محاسبه\u200cشده" in text
    expected = 234000 + Decimal("0.7") * (4 * 252000 + 8 * 196200) + 80 * 18000  # 3,478,320
    fa = f"{int(expected):,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert fa in text
    # no near-miss approximate bundles for providers with a rate table
    assert "g1-medium1" not in text


def test_vm_pending_providers_visible(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm")
    text = response.text
    for name in ("Liara", "ParsPack", "Cloud.ir"):
        assert name in text
    assert "هنوز گردآوری نشده" in text


def test_vm_foreign_region_plans_hidden_by_default(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm?tier=economy&size=medium")
    assert "c1-medium2" not in response.text  # eu-west plan excluded by Iran scope


def test_vm_calculated_discount_note_only_on_economy(client_tuple):
    client, _ = client_tuple
    economy = client.get("/vm?tier=economy&size=medium").text
    standard = client.get("/vm?tier=standard&size=medium").text
    premium = client.get("/vm?tier=premium&size=medium").text
    assert "تخفیف" in economy            # the 0.7 assumption applies to economy only
    assert "تخفیف" not in standard       # standard/premium use full published rates
    assert "تخفیف" not in premium


def test_plan_detail_shows_history_and_verification(client_tuple):
    client, g3_offering = client_tuple
    response = client.get(f"/plan/{g3_offering}")
    assert response.status_code == 200
    assert "تاریخچه قیمت" in response.text
    assert "g3-small1" in response.text


def test_status_page_lists_sources_and_runs(client_tuple):
    client = client_tuple[0]
    response = client.get("/status")
    assert response.status_code == 200
    assert "ArvanCloud" in response.text
    assert "موفق" in response.text or "هنوز اجرایی ثبت نشده" in response.text
