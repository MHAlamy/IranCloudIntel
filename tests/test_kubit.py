"""Tests for Kubit: rate parsing, rates-only pipeline, dashboard reflection."""

import json
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.kubit_rates import parse_kubit_rates  # noqa: E402
from comparison.rate_check import load_rate_mappings  # noqa: E402
from config.loader import ProviderConfig, SourceConfig  # noqa: E402
from extractors.llm import LLMClient  # noqa: E402
from storage.repository import Repository  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kubit_pricing"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def rates():
    html = (FIXTURES / "iaas_rates.html").read_text(encoding="utf-8")
    return parse_kubit_rates(html)


def test_parses_nine_rate_rows(rates):
    assert len(rates) == 9


def test_cpu_and_ram_by_generation(rates):
    by_key = {(r.category, r.tier_label): r.amount_toman for r in rates}
    assert by_key[("cpu", "gen-3")] == "249500"
    assert by_key[("cpu", "gen-4")] == "359500"
    assert by_key[("ram", "gen-3")] == "191510"
    assert by_key[("ram", "gen-4")] == "279510"
    assert by_key[("storage", "")] == "14900"


def test_ipv4_internet_and_floating(rates):
    by_label = {r.tier_label: r.amount_toman for r in rates if r.category == "ipv4"}
    assert by_label["internet"] == "173000"
    assert by_label["floating"] == "345000"


def test_free_upload_is_zero(rates):
    upload = next(r for r in rates if r.tier_label == "upload")
    assert upload.amount_toman == "0"


def test_kubit_mapping_decisions():
    mapping = load_rate_mappings()["kubit"]
    assert mapping.tier_generations == {"economy": "gen-3", "standard": "gen-4"}
    assert mapping.families == []  # no bundles to verify
    assert mapping.calculated_price_factors["economy"] == Decimal("1.0")


def test_calculated_baseline_prices():
    """Small/Medium gen-3 baselines incl. internet IPv4 (owner-approved math)."""
    small_gen3 = 249500 + 2 * 191510 + 20 * 14900 + 173000
    medium_gen3 = 4 * 249500 + 8 * 191510 + 80 * 14900 + 173000
    medium_gen4 = 4 * 359500 + 8 * 279510 + 80 * 14900 + 173000
    assert small_gen3 == 1103520
    assert medium_gen3 == 3895080
    assert medium_gen4 == 5039080


def test_pipeline_rates_only_source_no_llm(tmp_path):
    """Kubit-like source: rates parsed and stored, zero LLM calls, no bundles."""
    from collectors.kubit_clean import clean_kubit

    provider = ProviderConfig(slug="kubit", name="Kubit", official_url="https://kubit.cloud/")
    source = SourceConfig(
        id="kubit_vm_test", service_type="vm", url="https://kubit.cloud/fa/pricing",
        collection_method="http", region_scope="iran",
        navigation={"tabs": ["rates"], "bundle_extraction": False},
    )
    html = (ROOT / "evidence" / "kubit" / "vm").glob("*_pricing_http.html")
    page_html = sorted(html)[-1].read_text(encoding="utf-8")

    llm_calls: list[int] = []

    def failing_llm_factory():
        def handler(request: httpx.Request) -> httpx.Response:
            llm_calls.append(1)
            return httpx.Response(500)
        return LLMClient(base_url="https://mock.local/v1", api_key="k",
                         model="Test-Model", transport=httpx.MockTransport(handler))

    from collectors.pipeline import FetchResult, run_collection

    outcome = run_collection(
        provider, source, Repository(tmp_path / "t.db"),
        llm_factory=failing_llm_factory,
        fetcher=lambda s: FetchResult(html=page_html, http_status=200, final_url=s.url),
        cleaner=clean_kubit,
        rates_parser=parse_kubit_rates,
        rate_mappings=load_rate_mappings(),
        bundle_extraction=False,
        evidence_root=tmp_path / "evidence",
    )
    assert outcome.status == "success"
    assert outcome.detail.get("rates_stored") == 9
    assert llm_calls == []  # rates-only: LLM never called


def test_dashboard_reflects_kubit(client_tuple):
    """Seeded dashboard includes Kubit calculated rows (see client fixture seed)."""
    client, _ = client_tuple
    economy = client.get("/vm?tier=economy&size=medium").text
    standard = client.get("/vm?tier=standard&size=medium").text
    fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert "Kubit" in economy
    assert fa(3895080) in economy   # gen-3 Medium
    assert fa(5039080) in standard  # gen-4 Medium
    premium = client.get("/vm?tier=premium&size=medium").text
    assert fa(5039080) not in premium  # no premium offering for Kubit
