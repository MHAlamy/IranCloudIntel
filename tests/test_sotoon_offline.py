"""Sotoon offline VM price import: derivation, pipeline, and dashboard."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.vm_view import build_vm_view
from collectors.common import FetchError
from collectors.offline_pipeline import run_offline_collection
from collectors.sotoon_offline import build_collection, collect_sotoon_offline
from config.loader import load_benchmarks, load_providers
from storage.repository import Repository

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "datasets" / "offline" / "sotoon-price-1405-v3"

# Neda datacenter: E1 (shared) 1 vCPU + 2 GB = 11,200,000 IRR,
# C1 (dedicated) = 18,700,000 IRR, mana_2_premium disk = 205,000 IRR/GB.
SHARED_UNIT = Decimal("1120000")
DEDICATED_UNIT = Decimal("1870000")
DISK_PER_GB = Decimal("20500")

EXPECTED = {
    ("standard", "small"): SHARED_UNIT + 20 * DISK_PER_GB,
    ("standard", "medium"): 4 * SHARED_UNIT + 80 * DISK_PER_GB,
    ("standard", "large"): 16 * SHARED_UNIT + 320 * DISK_PER_GB,
    ("standard", "very_large"): 32 * SHARED_UNIT + 640 * DISK_PER_GB,
    ("premium", "small"): DEDICATED_UNIT + 20 * DISK_PER_GB,
    ("premium", "medium"): 4 * DEDICATED_UNIT + 80 * DISK_PER_GB,
    ("premium", "large"): 16 * DEDICATED_UNIT + 320 * DISK_PER_GB,
    ("premium", "very_large"): 32 * DEDICATED_UNIT + 640 * DISK_PER_GB,
}


def sotoon_config():
    provider = next(p for p in load_providers().providers if p.slug == "sotoon")
    return provider, provider.sources[0]


def fa(amount: int | Decimal) -> str:
    return f"{int(amount):,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def test_reference_prices_scale_from_the_one_vcpu_unit():
    collection = build_collection(
        PACKAGE, region="Neda", disk_sku="mana_2_premium",
        sizes=load_benchmarks().vm.sizes,
    )
    size_by_vcpu = {1: "small", 4: "medium", 16: "large", 32: "very_large"}
    tier_of = {"shared": "standard", "dedicated": "premium"}
    assert len(collection.plans) == 8
    for plan in collection.plans:
        key = (tier_of[plan.provider_tier_raw], size_by_vcpu[plan.vcpu])
        assert plan.price_toman == EXPECTED[key], key
        assert plan.region == "ir-neda"
        assert plan.disk_gb > 0
    assert collection.valid_until == "2027-03-20"
    assert "Sotoon price list" in collection.source_document


def test_evidence_keeps_page_source_and_validity():
    collection = build_collection(
        PACKAGE, region="Neda", disk_sku="mana_2_premium",
        sizes=load_benchmarks().vm.sizes,
    )
    medium = next(
        p for p in collection.plans if p.vcpu == 4 and p.provider_tier_raw == "shared"
    )
    assert "p.4" in medium.evidence
    assert "Neda" in medium.evidence
    assert "11,200,000 IRR" in medium.evidence
    assert "×4" in medium.evidence
    assert "205,000 IRR" in medium.evidence
    assert "mana_2_premium" in medium.evidence
    assert "end of Esfand 1405" in medium.evidence
    assert medium.disk_type == "دیسک مانا نوع ۲ (پرمیوم)"


def test_non_unit_reference_size_is_rejected():
    from config.loader import BenchmarkSize

    with pytest.raises(FetchError, match="not a multiple"):
        build_collection(
            PACKAGE, region="Neda", disk_sku="mana_2_premium",
            sizes={"odd": BenchmarkSize(vcpu=2, ram_gb=3, disk_gb=20)},
        )


def test_unknown_region_is_rejected():
    from config.loader import load_benchmarks

    with pytest.raises(FetchError, match="1 vCPU \\+ 2 GB"):
        build_collection(
            PACKAGE, region="Nowhere", disk_sku="mana_2_premium",
            sizes=load_benchmarks().vm.sizes,
        )


@pytest.fixture
def imported(tmp_path):
    db = tmp_path / "sotoon.db"
    repo = Repository(db)
    provider, source = sotoon_config()
    outcome = run_offline_collection(
        provider, source, repo, collect_sotoon_offline,
        evidence_root=tmp_path / "evidence",
    )
    yield repo, outcome, source, db
    repo.close()


def test_import_records_manual_provenance(imported):
    repo, outcome, source, _ = imported
    assert outcome.status == "success"
    assert outcome.observations == 8

    rows = repo.latest_observations(service_type="vm")
    assert {r["provider_slug"] for r in rows} == {"sotoon"}
    assert {r["collection_method"] for r in rows} == {"manual"}
    assert {r["source_document"] for r in rows} == {outcome.detail["source_document"]}
    assert {r["valid_until"] for r in rows} == {"2027-03-20"}

    run = repo._connection.execute(
        "SELECT source_document, valid_until FROM collection_runs WHERE status='success'"
    ).fetchone()
    assert run["valid_until"] == "2027-03-20"
    assert "Sotoon" in run["source_document"]


def test_second_import_is_skipped_when_unchanged(imported, tmp_path):
    repo, _, source, _ = imported
    provider, _ = sotoon_config()
    again = run_offline_collection(
        provider, source, repo, collect_sotoon_offline,
        evidence_root=tmp_path / "evidence2",
    )
    assert again.status == "success" and again.skipped is True


def test_view_marks_sotoon_rows_as_manual_calculated(imported):
    repo, _, _, _ = imported
    view = build_vm_view(repo, "standard", "small")
    row = next(r for r in view["rows"] if r.provider_slug == "sotoon")
    assert row.price_in_toman == EXPECTED[("standard", "small")]
    assert row.basis == "calculated"
    assert row.provenance == "manual"
    assert any("منبع دستی" in note for note in row.notes)
    assert any("معتبر تا" in note for note in row.notes)
    assert any("۱ برابر بسته‌ی" in note for note in row.notes)
    assert any("دیسک مانا نوع ۲ (پرمیوم)" in note for note in row.notes)
    assert row.disk_type == "دیسک مانا نوع ۲ (پرمیوم)"


def test_view_premium_uses_the_dedicated_unit(imported):
    repo, _, _, _ = imported
    view = build_vm_view(repo, "premium", "medium")
    row = next(r for r in view["rows"] if r.provider_slug == "sotoon")
    assert row.price_in_toman == EXPECTED[("premium", "medium")]
    assert row.plan_name == "4 vCPU + 8 GB (dedicated)"


@pytest.mark.parametrize(("day", "stale"), [(20, False), (21, True)])
def test_freshness_respects_document_expiry(imported, day, stale):
    from datetime import datetime, timezone

    repo, _, _, _ = imported
    now = datetime(2027, 3, day, tzinfo=timezone.utc)
    entry = next(e for e in repo.freshness("vm", now=now) if e["provider"] == "Sotoon")
    assert entry["collection_method"] == "manual"
    assert entry["valid_until"] == "2027-03-20"
    assert entry["stale"] is stale


def test_dashboard_renders_sotoon_with_manual_badge(imported):
    _, _, _, db = imported
    with TestClient(create_app(db)) as client:
        text = client.get("/vm?tier=standard&size=small").text
        assert "Sotoon" in text
        assert fa(EXPECTED[("standard", "small")]) in text
        assert "badge-manual" in text and "دستی" in text
        assert "منبع دستی" in text
        assert "۱۴۰۵/۱۲/۲۹" in text  # validity shown in Jalali

        status = client.get("/status").text
        assert "منبع دستی" in status


def test_plan_detail_keeps_document_and_page(imported):
    repo, _, _, db = imported
    offering_id = repo._connection.execute(
        """SELECT off.id FROM offerings off JOIN providers p ON p.id = off.provider_id
           WHERE p.slug='sotoon' AND off.plan_name='4 vCPU + 8 GB (shared)'"""
    ).fetchone()["id"]
    with TestClient(create_app(db)) as client:
        text = client.get(f"/plan/{offering_id}").text
        assert "منبع دستی" in text
        assert "معتبر تا ۱۴۰۵/۱۲/۲۹" in text
        assert "Sotoon price list v3 p.4 (Neda)" in text  # evidence keeps the page
        assert "E1 shared" in text
        assert "دیسک مانا نوع ۲ (پرمیوم)" in text
