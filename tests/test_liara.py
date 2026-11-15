"""Tests for Liara: bundle parsing, IPv4 surcharge, pipeline, dashboard."""

import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.liara_clean import clean_liara  # noqa: E402
from collectors.liara_plans import parse_ipv4_monthly, parse_liara_plans  # noqa: E402
from config.loader import ProviderConfig, SourceConfig  # noqa: E402
from extractors.llm import LLMClient  # noqa: E402
from storage.repository import Repository  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "liara_vm"
EVIDENCE = ROOT / "evidence" / "liara" / "vm"


@pytest.fixture(scope="module")
def product_html() -> str:
    snap = sorted(EVIDENCE.glob("*_product.html"))[-1]
    return snap.read_text(encoding="utf-8")


def test_parses_six_plans(product_html):
    plans = parse_liara_plans(product_html)
    assert [p.name for p in plans] == ["مشتری", "زحل", "اورانوس", "نپتون", "پلوتون", "اریس"]
    by_name = {p.name: p for p in plans}
    assert by_name["مشتری"].monthly_toman == "1475000"
    assert by_name["مشتری"].vcpu == "1" and by_name["مشتری"].ram_gb == "2" and by_name["مشتری"].disk_gb == "20"
    assert by_name["اورانوس"].monthly_toman == "4600000"
    assert by_name["اورانوس"].vcpu == "4" and by_name["اورانوس"].ram_gb == "8" and by_name["اورانوس"].disk_gb == "80"
    assert by_name["اریس"].vcpu == "32" and by_name["اریس"].ram_gb == "64" and by_name["اریس"].disk_gb == "640"


def test_ipv4_surcharge_parsed_from_page(product_html):
    assert parse_ipv4_monthly(product_html) == "200000"


def test_pricing_page_yields_same_plans():
    snap = sorted(EVIDENCE.glob("*_pricing.html"))[-1]
    plans = parse_liara_plans(snap.read_text(encoding="utf-8"))
    assert [p.name for p in plans] == ["مشتری", "زحل", "اورانوس", "نپتون", "پلوتون", "اریس"]
    assert plans[0].monthly_toman == "1475000"


def test_paas_section_not_confused_with_iaas(product_html):
    """PaaS 'پلوتون' is 22,000,000 — the parser must store the IaaS 14,000,000."""
    plans = {p.name: p for p in parse_liara_plans(product_html)}
    assert plans["پلوتون"].monthly_toman == "14000000"


def test_clean_liara_deterministic(product_html):
    url = "https://liara.ir/products/cloud-server/"
    md1 = clean_liara(product_html, url, ["plans"])["plans"]
    md2 = clean_liara(product_html, url, ["plans"])["plans"]
    assert md1.markdown == md2.markdown
    assert md1.content_hash == md2.content_hash


def test_pipeline_liara_records_bundles_with_ipv4(tmp_path):
    provider = ProviderConfig(slug="liara", name="Liara", official_url="https://liara.ir/")
    source = SourceConfig(
        id="liara_vm_test", service_type="vm", url="https://liara.ir/products/cloud-server/",
        collection_method="http", region_scope="iran",
        navigation={"tabs": ["plans"], "bundle_extraction": False},
    )
    product_html = sorted(EVIDENCE.glob("*_product.html"))[-1].read_text(encoding="utf-8")

    llm_calls: list[int] = []

    def counting_llm_factory():
        def handler(request: httpx.Request) -> httpx.Response:
            llm_calls.append(1)
            return httpx.Response(500)
        return LLMClient(base_url="https://mock.local/v1", api_key="k",
                         model="Test-Model", transport=httpx.MockTransport(handler))

    from collectors.pipeline import FetchResult, run_collection

    repo = Repository(tmp_path / "t.db")
    try:
        outcome = run_collection(
            provider, source, repo,
            llm_factory=counting_llm_factory,
            fetcher=lambda s: FetchResult(html=product_html, http_status=200, final_url=s.url),
            cleaner=clean_liara,
            rate_mappings={},
            bundle_extraction=False,
            plans_parser=parse_liara_plans,
            evidence_root=tmp_path / "evidence",
        )
        assert outcome.status == "success"
        assert outcome.observations == 6
        assert llm_calls == []  # deterministic: no LLM

        latest = {row["plan_name"]: row for row in repo.latest_observations(service_type="vm")}
        # comparable price = monthly + documented 200,000 IPv4
        assert latest["اورانوس"]["price_in_toman"] == "4800000"
        assert latest["مشتری"]["price_in_toman"] == "1675000"
        assert latest["اریس"]["price_in_toman"] == "24800000"
        # raw monthly preserved in price_raw (typography-agnostic check)
        from normalization.persian import parse_price

        assert parse_price(latest["اورانوس"]["price_raw"]) == Decimal(4600000)
        assert latest["اورانوس"]["region"] == "ir-iran"
        assert latest["اورانوس"]["provider_slug"] == "liara"
    finally:
        repo.close()


def test_dashboard_reflects_liara(client_tuple):
    client, _ = client_tuple
    fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    standard_medium = client.get("/vm?tier=standard&size=medium").text
    assert "Liara" in standard_medium
    assert fa(4800000) in standard_medium  # اورانوس + IPv4, exact baseline
    standard_vl = client.get("/vm?tier=standard&size=very_large").text
    assert fa(24800000) in standard_vl  # اریس + IPv4, exact baseline
