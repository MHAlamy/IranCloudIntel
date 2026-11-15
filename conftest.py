"""Shared fixtures: seeded dashboard app + test client (module-scope)."""

import sys
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors.arvan_rates import RateRow
from extractors.schema import LLMPlanRow, NormalizedPlanRow
from storage.repository import Repository

from app.main import create_app


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

    # Arvan rates (subset used by calculated pricing and verification)
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

    # Kubit: rates-only provider (no bundles); gen-3 → economy, gen-4 → standard
    kubit = repo.ensure_provider("kubit", "Kubit", "https://kubit.cloud/")
    kubit_source = repo.ensure_source(kubit, "vm", "https://kubit.cloud/fa/pricing", "http")
    kubit_rates = [
        RateRow("cpu", "iran", "هر vCPU", "gen-3", "249500", ""),
        RateRow("cpu", "iran", "هر vCPU", "gen-4", "359500", ""),
        RateRow("ram", "iran", "هر گیگابایت", "gen-3", "191510", ""),
        RateRow("ram", "iran", "هر گیگابایت", "gen-4", "279510", ""),
        RateRow("storage", "iran", "هر گیگابایت", "", "14900", ""),
        RateRow("ipv4", "iran", "هر آدرس", "internet", "173000", ""),
    ]
    kubit_run = repo.start_run(kubit_source)
    repo.finish_run(kubit_run, "success", model="", prompt_tokens=0, completion_tokens=0)
    repo.record_rates(kubit_run, kubit, kubit_rates)

    # Liara: fixed-bundle provider, all plans Standard tier, exact baselines.
    # Comparable price = published monthly + documented 200,000 IPv4 surcharge.
    liara = repo.ensure_provider("liara", "Liara", "https://liara.ir/")
    liara_source = repo.ensure_source(
        liara, "vm", "https://liara.ir/products/cloud-server/", "http"
    )
    liara_run = repo.start_run(liara_source)
    repo.finish_run(liara_run, "success", model="", prompt_tokens=0, completion_tokens=0)
    liara_plans = [
        ("مشتری", 1, 2, 20, "1475000"),
        ("زحل", 2, 4, 40, "2650000"),
        ("اورانوس", 4, 8, 80, "4600000"),
        ("نپتون", 8, 16, 160, "8000000"),
        ("پلوتون", 16, 32, 320, "14000000"),
        ("اریس", 32, 64, 640, "24600000"),
    ]
    for plan_name, vcpu, ram, disk, monthly in liara_plans:
        offering = repo.ensure_offering(
            liara, "vm", plan_name, product_family="fixed_bundle",
            provider_tier_raw="standard", region="ir-iran",
        )
        raw = LLMPlanRow(
            plan_name=plan_name, provider_tier_raw="standard", region="ir-iran",
            vcpu=vcpu, ram_gb=float(ram), disk_gb=float(disk), disk_type=None,
            price_raw="۱", currency_raw="تومان", billing_period_raw="ماهانه", evidence="e",
        )
        normalized = NormalizedPlanRow(
            plan_name=plan_name, provider_tier_raw="standard", region="ir-iran",
            vcpu=vcpu, ram_gb=Decimal(ram), disk_gb=Decimal(disk), disk_type=None,
            price_value=Decimal(monthly), currency="toman",
            price_in_toman=Decimal(monthly) + Decimal("200000"),
            billing_period="monthly", pricing_type="fixed_bundle",
            validation_status="valid", validation_issues=[],
        )
        repo.record_observation(liara_run, offering, raw, normalized, evidence="e")

    # ParsPack: calculator quotes for the baseline configs (monthly comparable
    # prices incl. 150,000 IPv4 and 5% monthly discount, per analyst facts)
    parspack = repo.ensure_provider("parspack", "ParsPack", "https://parspack.com/")
    parspack_source = repo.ensure_source(
        parspack, "vm", "https://parspack.com/cloud-server", "playwright"
    )
    parspack_run = repo.start_run(parspack_source)
    repo.finish_run(parspack_run, "success", model="", prompt_tokens=0, completion_tokens=0)
    parspack_quotes = [
        ("1vCPU-2GB-25GB", 1, 2, 25, "1227300"),
        ("4vCPU-8GB-80GB", 4, 8, 80, "3408120"),
        ("16vCPU-32GB-300GB", 16, 32, 300, "12648810"),
        ("32vCPU-64GB-300GB", 32, 64, 300, "24349065"),
    ]
    for plan_name, vcpu, ram, disk, monthly in parspack_quotes:
        offering = repo.ensure_offering(
            parspack, "vm", plan_name, product_family="calculator_quote",
            provider_tier_raw="standard", region="ir-tehran11",
        )
        raw = LLMPlanRow(
            plan_name=plan_name, provider_tier_raw="standard", region="ir-tehran11",
            vcpu=vcpu, ram_gb=float(ram), disk_gb=float(disk), disk_type=None,
            price_raw="۱", currency_raw="تومان", billing_period_raw="روزانه", evidence="e",
        )
        normalized = NormalizedPlanRow(
            plan_name=plan_name, provider_tier_raw="standard", region="ir-tehran11",
            vcpu=vcpu, ram_gb=Decimal(ram), disk_gb=Decimal(disk), disk_type=None,
            price_value=Decimal(monthly), currency="toman", price_in_toman=Decimal(monthly),
            billing_period="monthly", pricing_type="configurable_quote",
            validation_status="valid", validation_issues=[],
        )
        repo.record_observation(parspack_run, offering, raw, normalized, evidence="e")
