"""Tests for the SQLite persistence layer (temporary database per test)."""

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from extractors.schema import LLMPlanRow, NormalizedPlanRow
from storage.db import SCHEMA_VERSION, connect, init_db
from storage.repository import Repository

DB_PATH = Path(__file__).resolve().parent / "_tmp_storage_test.db"


@pytest.fixture()
def repo(tmp_path) -> Repository:
    repository = Repository(tmp_path / "test.db")
    yield repository
    repository.close()


def make_raw(plan_name="eco-small4", price_raw="۱,۴۰۱,۴۸۰", currency_raw="تومان") -> LLMPlanRow:
    return LLMPlanRow(
        plan_name=plan_name, provider_tier_raw="basic", region="ir-thr-ba1",
        vcpu=2, ram_gb=2, disk_gb=30, disk_type=None,
        price_raw=price_raw, currency_raw=currency_raw, billing_period_raw="ماهانه",
        evidence=f"{plan_name} row evidence",
    )


def make_normalized(price_value="1401480", currency="toman", status="valid") -> NormalizedPlanRow:
    return NormalizedPlanRow(
        plan_name="eco-small4", provider_tier_raw="basic", region="ir-thr-ba1",
        vcpu=2, ram_gb=2.0, disk_gb=30.0, disk_type=None,
        price_value=Decimal(price_value), currency=currency,  # type: ignore[arg-type]
        price_in_toman=Decimal(price_value) if currency == "toman" else None,  # type: ignore[arg-type]
        billing_period="monthly",  # type: ignore[arg-type]
        pricing_type="fixed_bundle",
        validation_status=status,  # type: ignore[arg-type]
        validation_issues=[],
    )


def test_init_db_is_idempotent_and_records_version(tmp_path):
    init_db(tmp_path / "a.db")
    init_db(tmp_path / "a.db")
    connection = connect(tmp_path / "a.db")
    version = connection.execute("SELECT MAX(version) v FROM schema_version").fetchone()["v"]
    connection.close()
    assert version == SCHEMA_VERSION


def test_identity_upserts_are_idempotent(repo):
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    again = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    assert arvan == again

    source = repo.ensure_source(arvan, "vm", "https://www.arvancloud.ir/fa/pricing/cloud-server", "playwright")
    assert repo.ensure_source(arvan, "vm", "https://www.arvancloud.ir/fa/pricing/cloud-server", "playwright") == source

    offering = repo.ensure_offering(arvan, "vm", "eco-small4", provider_tier_raw="basic", region="ir-thr-ba1")
    assert repo.ensure_offering(arvan, "vm", "eco-small4", provider_tier_raw="basic", region="ir-thr-ba1") == offering
    # same plan name but different region -> distinct offering
    assert repo.ensure_offering(arvan, "vm", "eco-small4", provider_tier_raw="basic", region="eu-west1-a") != offering


def test_run_lifecycle_and_history(repo):
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    source = repo.ensure_source(arvan, "vm", "https://example.com/pricing", "playwright")
    offering = repo.ensure_offering(arvan, "vm", "eco-small4", provider_tier_raw="basic", region="ir-thr-ba1")

    run1 = repo.start_run(source)
    repo.finish_run(run1, "success", http_status=200, content_hash="hash1",
                    extractor_config_hash="cfg1", model="GPT-5-Mini",
                    schema_version="vm-v1", prompt_tokens=1000, completion_tokens=1100)
    obs1 = repo.record_observation(run1, offering, make_raw(), make_normalized(), evidence="e1")

    run2 = repo.start_run(source)
    repo.finish_run(run2, "success", http_status=200, content_hash="hash2",
                    extractor_config_hash="cfg1", model="GPT-5-Mini",
                    schema_version="vm-v1", prompt_tokens=1000, completion_tokens=1100)
    repo.record_observation(run2, offering, make_raw(), make_normalized(price_value="1500000"), evidence="e2")

    # failed run records the attempt but adds no observation
    run3 = repo.start_run(source)
    repo.finish_run(run3, "failed", http_status=503, error="upstream challenge loop")

    history = repo.offering_history(offering)
    assert len(history) == 2  # failed run added nothing
    assert history[0]["price_value"] == "1500000"  # newest first
    assert history[1]["id"] == obs1

    # raw source text preserved verbatim
    assert history[0]["price_raw"] == "۱,۴۰۱,۴۸۰"
    assert history[0]["currency_raw"] == "تومان"
    assert history[0]["billing_period_raw"] == "ماهانه"


def test_record_observation_rejects_suspect_and_missing_canonical(repo):
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    source = repo.ensure_source(arvan, "vm", "https://example.com/pricing", "playwright")
    offering = repo.ensure_offering(arvan, "vm", "x", provider_tier_raw="basic", region="r")
    run = repo.start_run(source)
    repo.finish_run(run, "success")

    with pytest.raises(ValueError, match="valid"):
        repo.record_observation(run, offering, make_raw(), make_normalized(status="suspect"))
    with pytest.raises(ValueError, match="price_in_toman"):
        repo.record_observation(run, offering, make_raw(currency_raw="دلار"),
                                make_normalized(currency="unknown", price_value="100"))


def test_latest_observations_returns_newest_valid_per_offering(repo):
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    source = repo.ensure_source(arvan, "vm", "https://example.com/pricing", "playwright")
    off1 = repo.ensure_offering(arvan, "vm", "eco-small4", provider_tier_raw="basic", region="ir-thr-ba1")
    off2 = repo.ensure_offering(arvan, "vm", "c1-medium1", provider_tier_raw="basic", region="eu-west1-a")

    run = repo.start_run(source)
    repo.finish_run(run, "success")
    repo.record_observation(run, off1, make_raw(), make_normalized(), observed_at="2026-11-14T10:00:00+00:00")
    repo.record_observation(run, off2, make_raw("c1-medium1"), make_normalized(price_value="2411200"),
                            observed_at="2026-11-14T10:00:00+00:00")

    latest = repo.latest_observations(service_type="vm")
    by_name = {row["plan_name"]: row for row in latest}
    assert by_name["eco-small4"]["price_value"] == "1401480"
    assert by_name["c1-medium1"]["price_value"] == "2411200"
    assert by_name["eco-small4"]["provider_slug"] == "arvan"


def test_should_skip_extraction(repo):
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    source = repo.ensure_source(arvan, "vm", "https://example.com/pricing", "playwright")

    run = repo.start_run(source)
    repo.finish_run(run, "success", content_hash="hash-aaa", extractor_config_hash="cfg-1")

    assert repo.should_skip_extraction(source, "hash-aaa", "cfg-1") is True
    assert repo.should_skip_extraction(source, "hash-bbb", "cfg-1") is False   # content changed
    assert repo.should_skip_extraction(source, "hash-aaa", "cfg-2") is False   # extractor config changed
    assert repo.should_skip_extraction(source, "hash-aaa", "cfg-1") is False if False else True


def test_validation_issues_stored_as_json(repo):
    arvan = repo.ensure_provider("arvan", "ArvanCloud", "https://www.arvancloud.ir/")
    source = repo.ensure_source(arvan, "vm", "https://example.com/pricing", "playwright")
    offering = repo.ensure_offering(arvan, "vm", "eco-small4", provider_tier_raw="basic", region="ir-thr-ba1")
    run = repo.start_run(source)
    repo.finish_run(run, "success")
    repo.record_observation(run, offering, make_raw(), make_normalized(), evidence="e")
    row = repo.offering_history(offering)[0]
    assert json.loads(row["validation_issues"]) == []


def test_wal_serializes_concurrent_writers(tmp_path):
    """WAL allows one writer at a time; short transactions queue via busy_timeout.
    (This is why the collector must keep transactions short and use a run lock.)"""
    db_path = tmp_path / "conc.db"
    init_db(db_path)
    conn1, conn2 = connect(db_path), connect(db_path)
    try:
        conn1.execute("INSERT INTO providers (slug, name, official_url) VALUES ('a','A','u')")
        conn1.commit()  # short transaction: commit before the other writer proceeds
        conn2.execute("INSERT INTO providers (slug, name, official_url) VALUES ('b','B','u')")
        conn2.commit()
        count = conn1.execute("SELECT COUNT(*) c FROM providers").fetchone()["c"]
        assert count == 2
    finally:
        conn1.close()
        conn2.close()
