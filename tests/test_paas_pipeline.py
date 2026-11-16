"""PaaS collection pipeline: fake collectors, no network calls."""
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.paas_pipeline import PaasCollection, PaasQuote, run_paas_collection  # noqa: E402
from config.loader import ProviderConfig, SourceConfig  # noqa: E402
from storage.repository import Repository  # noqa: E402


def _provider(slug: str, source_id: str) -> ProviderConfig:
    return ProviderConfig(
        slug=slug,
        name=slug.title(),
        official_url=f"https://{slug}.example/",
        sources=[SourceConfig(
            id=source_id,
            service_type="paas",
            url=f"https://{slug}.example/pricing",
            collection_method="http",
            region_scope="iran",
            navigation={},
        )],
    )


def _quote(plan_name="1 vCPU + 2 GB RAM") -> PaasQuote:
    return PaasQuote(
        plan_name=plan_name,
        vcpu=1,
        ram_gb=Decimal("2"),
        disk_gb=Decimal("20"),
        price_toman=Decimal("2395440"),
        price_raw="۲٬۳۹۵٬۴۴۰ تومان",
        provider_tier_raw="payg",
        region="ir-thr-ba1",
        product_family="paas_calculated",
        pricing_type="configurable_quote",
        evidence="fixture rate calculation",
    )


@pytest.fixture()
def repo(tmp_path):
    repository = Repository(tmp_path / "paas.db")
    yield repository
    repository.close()


def test_paas_collection_records_then_skips_unchanged(repo, tmp_path):
    provider = _provider("arvan", "arvan_paas")
    source = provider.sources[0]
    quote = _quote()

    def collector(src):
        assert src.id == "arvan_paas"
        return PaasCollection(quotes=[quote], cleaned="# fixture\n")

    first = run_paas_collection(
        provider, source, repo, collector, evidence_root=tmp_path
    )
    assert first.status == "success" and first.error is None
    assert first.observations == 1

    rows = repo.latest_observations(service_type="paas")
    assert len(rows) == 1
    assert rows[0]["provider_slug"] == "arvan"
    assert Decimal(rows[0]["price_in_toman"]) == Decimal("2395440")
    assert rows[0]["vcpu"] == 1
    assert Decimal(rows[0]["disk_gb"]) == Decimal("20")

    second = run_paas_collection(
        provider, source, repo, collector, evidence_root=tmp_path
    )
    assert second.status == "success" and second.skipped
    assert len(repo.latest_observations(service_type="paas")) == 1


def test_paas_empty_collection_is_a_visible_failure(repo, tmp_path):
    provider = _provider("arvan", "arvan_paas")
    source = provider.sources[0]
    outcome = run_paas_collection(
        provider, source, repo, lambda src: PaasCollection(quotes=[]),
        evidence_root=tmp_path,
    )
    assert outcome.status == "failed"
    assert "no accepted PaaS quotes" in outcome.error
    assert not repo.latest_observations(service_type="paas")


def test_paas_service_type_is_allowed_by_schema(repo):
    provider = repo.ensure_provider("paas_test", "PaaS Test", "https://paas.example/")
    source = repo.ensure_source(provider, "paas", "https://paas.example/pricing", "http")
    offering = repo.ensure_offering(
        provider, "paas", "1 vCPU + 2 GB RAM",
        product_family="paas_calculated", provider_tier_raw="payg", region="ir-iran",
    )
    assert source > 0 and offering > 0
