"""Tests for Kubit: rate parsing, rates-only pipeline, dashboard reflection."""

import json
import sys
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.kubit_rates import parse_kubit_rates  # noqa: E402
from config.loader import load_analyst_facts
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


def test_near_miss_exact_cpu_ram_shows_as_approximate():
    """Providers without rates (e.g. ParsPack quotes): exact CPU/RAM with a
    different disk is a near miss — shown as تقریبی by the app layer."""
    from comparison.matching import VMMatcher
    from config.loader import load_benchmarks, load_tiers

    matcher = VMMatcher(load_benchmarks(), load_tiers())

    def plan(name, tier_raw, region, vcpu, ram, disk, price):
        from decimal import Decimal as D

        from comparison.matching import PlanView

        return PlanView(
            provider_slug="parspack", plan_name=name,
            tier=matcher.normalize_tier("parspack", tier_raw),
            region=region, vcpu=vcpu, ram_gb=D(ram), disk_gb=D(disk),
            price_in_toman=D(price), observed_at="2026-11-15T12:00:00+00:00",
            validation_status="valid",
        )
    quotes = [
        plan("4vCPU-8GB-80GB", "standard", "ir-tehran11", 4, 8, 80, 3408120),
        plan("1vCPU-2GB-25GB", "standard", "ir-tehran11", 1, 2, 25, 1227300),
        plan("16vCPU-32GB-300GB", "standard", "ir-tehran11", 16, 32, 300, 12648810),
        plan("32vCPU-64GB-300GB", "standard", "ir-tehran11", 32, 64, 300, 24349065),
    ]
    # Medium: exact baseline bundle -> primary
    medium = matcher.match_size(quotes, "standard", "medium")
    assert [m.plan.plan_name for m in medium.primary] == ["4vCPU-8GB-80GB"]
    # Small: 1/2/25 is a near miss (disk +5)
    small = matcher.match_size(quotes, "standard", "small")
    assert small.primary == []
    assert [m.plan.plan_name for m in small.near_miss] == ["1vCPU-2GB-25GB"]
    # VeryLarge (32/64/640): 32/64/300 has exact CPU/RAM, disk differs -> near miss
    very_large = matcher.match_size(quotes, "standard", "very_large")
    assert very_large.primary == []
    assert [m.plan.plan_name for m in very_large.near_miss] == ["32vCPU-64GB-300GB"]


def test_parspack_monthly_computation():
    from collectors.parspack_quotes import compute_monthly
    from config.loader import load_analyst_facts

    facts = load_analyst_facts()["parspack"]
    # Medium daily 114,320 -> x30 x0.95 = 3,258,120 + 150,000 IPv4 = 3,408,120
    assert compute_monthly(Decimal("114320"), facts) == Decimal("3408120")
    # Small daily 37,800 -> 1,077,300 + 150,000 = 1,227,300
    assert compute_monthly(Decimal("37800"), facts) == Decimal("1227300")


def test_parspack_slider_positions():
    from collectors.parspack_quotes import (
        nearest_cpu_position, nearest_disk_position, nearest_ram_position,
    )
    assert nearest_ram_position(8) == 2 and nearest_ram_position(64) == 5
    assert nearest_disk_position(80) == 11 and nearest_disk_position(20) == 0
    assert nearest_disk_position(320) == 59  # clamped by caller / actual read back
    assert nearest_cpu_position(4) == 3 and nearest_cpu_position(32) == 16
    assert nearest_cpu_position(16) == 15


def test_analyst_facts_load():
    facts = load_analyst_facts()["parspack"]
    assert facts.ipv4_monthly_toman == Decimal("150000")
    assert facts.monthly_discount == Decimal("0.95")
    assert facts.month_days == 30
    assert [q.label for q in facts.quotes] == ["small", "medium", "large", "very_large"]


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
