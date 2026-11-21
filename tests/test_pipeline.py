"""End-to-end collector pipeline tests with mocked fetching and mocked LLM."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from collectors.arvan_rates import RateRow
from collectors.pipeline import CollectionOutcome, FetchResult, extractor_config_hash, run_collection
from comparison.rate_check import ProviderRateMapping
from config.loader import ProviderConfig, SourceConfig
from extractors.llm import LLMClient
from storage.repository import Repository

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arvan_cloud_server"
ROOT = Path(__file__).resolve().parent.parent


def make_source(tabs=("basic",)) -> tuple[ProviderConfig, SourceConfig]:
    provider = ProviderConfig(slug="arvan", name="ArvanCloud", official_url="https://www.arvancloud.ir/")
    source = SourceConfig(
        id="arvan_vm_test", service_type="vm",
        url="https://www.arvancloud.ir/fa/pricing/cloud-server",
        collection_method="playwright", region_scope="iran",
        navigation={"ready_marker": "eco-small", "tabs": list(tabs)},
    )
    return provider, source


def fake_fetcher(panel_file: str = "panel_basic.html"):
    html = (FIXTURES / panel_file).read_text(encoding="utf-8")
    calls = {"count": 0}

    def fetch(source: SourceConfig):
        calls["count"] += 1
        return FetchResult(html=html, http_status=200, final_url=source.url)

    fetch.calls = calls
    return fetch


def mock_llm_factory(calls: list[int]):
    rows = json.loads((FIXTURES / "llm_rows_basic.json").read_text(encoding="utf-8"))["rows"]
    content = json.dumps({"rows": rows}, ensure_ascii=False)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "index": 0,
                         "message": {"role": "assistant", "content": content}}],
            "model": "Test-Model",
            "usage": {"prompt_tokens": 100, "completion_tokens": 200,
                      "completion_tokens_details": {"reasoning_tokens": 0}},
        })

    return lambda: LLMClient(base_url="https://mock.local/v1", api_key="k",
                             model="Test-Model", transport=httpx.MockTransport(handler))


def arvan_cleaner(html, url, tabs):
    from collectors.arvan_clean import clean_page

    return clean_page(html, url, tabs)


@pytest.fixture()
def repo(tmp_path):
    repository = Repository(tmp_path / "test.db")
    yield repository
    repository.close()


def test_first_run_extracts_and_records(repo, tmp_path):
    provider, source = make_source()
    llm_calls: list[int] = []
    outcome = run_collection(
        provider, source, repo, mock_llm_factory(llm_calls),
        fetcher=fake_fetcher(), cleaner=arvan_cleaner,
        evidence_root=tmp_path / "evidence",
    )
    assert outcome.status == "success" and not outcome.skipped
    assert outcome.observations == 8 and outcome.suspect_rows == 0
    assert outcome.prompt_tokens == 100 and outcome.completion_tokens == 200
    assert len(llm_calls) == 1

    latest = repo.latest_observations(service_type="vm")
    assert len(latest) == 8
    prices = {row["plan_name"]: row["price_in_toman"] for row in latest}
    assert prices["eco-small4"] == "1401480"
    assert prices["c1-medium1"] == "2411200"
    # cleaned content saved as evidence
    saved = list((tmp_path / "evidence").rglob("cleaned.md"))
    assert len(saved) == 1


def test_second_run_skips_llm_when_content_unchanged(repo, tmp_path):
    provider, source = make_source()
    llm_calls: list[int] = []
    factory = mock_llm_factory(llm_calls)
    run_collection(provider, source, repo, factory, fetcher=fake_fetcher(),
                   cleaner=arvan_cleaner, evidence_root=tmp_path / "evidence")
    assert len(llm_calls) == 1

    outcome2 = run_collection(provider, source, repo, factory, fetcher=fake_fetcher(),
                              cleaner=arvan_cleaner, evidence_root=tmp_path / "evidence")
    assert outcome2.skipped is True and outcome2.observations == 0
    assert len(llm_calls) == 1  # no additional LLM call

    outcome3 = run_collection(provider, source, repo, factory, fetcher=fake_fetcher(),
                              cleaner=arvan_cleaner, evidence_root=tmp_path / "evidence", force=True)
    assert outcome3.skipped is False and outcome3.observations == 8
    assert len(llm_calls) == 2


def test_changed_extractor_config_forces_reextraction(repo, tmp_path, monkeypatch):
    provider, source = make_source()
    llm_calls: list[int] = []
    factory = mock_llm_factory(llm_calls)
    monkeypatch.setenv("AIaaS_MODEL", "Test-Model")
    run_collection(provider, source, repo, factory, fetcher=fake_fetcher(),
                   cleaner=arvan_cleaner, evidence_root=tmp_path / "evidence")
    monkeypatch.setenv("AIaaS_MODEL", "Other-Model")
    outcome = run_collection(provider, source, repo, factory, fetcher=fake_fetcher(),
                             cleaner=arvan_cleaner, evidence_root=tmp_path / "evidence")
    assert outcome.skipped is False and len(llm_calls) == 2


def test_fetch_failure_records_failed_run_without_observations(repo, tmp_path):
    provider, source = make_source()

    def broken_fetcher(source: SourceConfig):
        raise RuntimeError("network down")

    outcome = run_collection(provider, source, repo, mock_llm_factory([]),
                             fetcher=broken_fetcher, cleaner=arvan_cleaner,
                             evidence_root=tmp_path / "evidence")
    assert outcome.status == "failed" and outcome.observations == 0
    assert "network down" in outcome.error

    # failed run left no observations and no successful skip-hash behind
    assert repo.latest_observations(service_type="vm") == []
    assert not repo.should_skip_extraction(1, "any", "any")


def test_extractor_config_hash_changes_with_model(monkeypatch):
    monkeypatch.setenv("AIaaS_MODEL", "A")
    h1 = extractor_config_hash("A")
    h2 = extractor_config_hash("B")
    assert h1 != h2


def test_suspect_rows_go_to_review_queue_not_history(repo, tmp_path):
    provider, source = make_source()
    rows = json.loads((FIXTURES / "llm_rows_basic.json").read_text(encoding="utf-8"))["rows"]
    bad_rows = rows + [{
        "plan_name": "mystery", "provider_tier_raw": "basic", "region": None,
        "vcpu": None, "ram_gb": None, "disk_gb": None, "disk_type": None,
        "price_raw": "۱۰۰", "currency_raw": "دلار", "billing_period_raw": "نامشخص",
        "evidence": "mystery",
    }]
    content = json.dumps({"rows": bad_rows}, ensure_ascii=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "index": 0,
                         "message": {"role": "assistant", "content": content}}],
            "model": "Test-Model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20,
                      "completion_tokens_details": {"reasoning_tokens": 0}},
        })

    factory = lambda: LLMClient(base_url="https://mock.local/v1", api_key="k",
                                model="Test-Model", transport=httpx.MockTransport(handler))
    outcome = run_collection(provider, source, repo, factory, fetcher=fake_fetcher(),
                             cleaner=arvan_cleaner, evidence_root=tmp_path / "evidence")
    assert outcome.observations == 8 and outcome.suspect_rows == 1
    assert repo.latest_observations(service_type="vm")
    review_files = list((tmp_path / "evidence").rglob("review_queue.json"))
    assert len(review_files) == 1
    assert "mystery" in review_files[0].read_text(encoding="utf-8")


def test_missing_ipv4_rate_marks_review_instead_of_failing(repo, tmp_path):
    provider, source = make_source()
    rates = [
        RateRow("cpu", "iran", "هر vCore", "Basic", "100", ""),
        RateRow("ram", "iran", "هر گیگابایت", "Basic", "50", ""),
        RateRow("storage", "iran", "هر گیگابایت", "بلاک استوریج (Eco)", "10", ""),
    ]
    mapping = ProviderRateMapping(
        provider_slug="arvan", families=[], calculated_price_factors={},
    )
    outcome = run_collection(
        provider, source, repo, mock_llm_factory([]),
        fetcher=fake_fetcher(), cleaner=arvan_cleaner,
        evidence_root=tmp_path / "evidence",
        rates_parser=lambda html: rates,
        rate_mappings={"arvan": mapping},
    )
    assert outcome.status == "success"
    latest = repo.latest_observations(service_type="vm")
    assert latest and {row["rate_verification"] for row in latest} == {"review"}
