"""DBaaS collection pipeline.

DBaaS prices are compute-shaped, so they reuse the existing
`price_observations` table with `service_type='dbaas'`. Two infrastructure
classes are collected from the same provider page. `product_family` records the
class and the price basis, e.g. `dbaas_local_calculated` or
`dbaas_shared_published`, so the dashboard can keep both classes apart without
adding a new pricing table.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable

from collectors.common import (
    CollectionOutcome,
    FetchError,
    content_hash,
    fail_collection,
    raw_and_normalized,
    start_collection,
    write_evidence,
)
from config.loader import ProviderConfig, SourceConfig, load_benchmarks
from storage.repository import Repository
from util.fingerprint import collection_fingerprint
from util.format import format_toman

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = ROOT / "evidence"
DBAAS_SCHEMA_VERSION = "dbaas-v1"
DBAAS_CLASSES = ("local", "shared")
DBAAS_BASES = ("published", "calculated")


@dataclass
class DbaasQuote:
    """One comparable DBaaS quote for a reference size and infrastructure class."""

    plan_name: str
    infra_class: str  # local | shared
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    price_toman: Decimal
    price_raw: str
    provider_tier_raw: str
    region: str
    pricing_type: str  # fixed_bundle | configurable_quote
    evidence: str
    disk_type: str
    basis: str = "calculated"  # published | calculated
    notes: list[str] = field(default_factory=list)

    @property
    def product_family(self) -> str:
        if self.infra_class not in DBAAS_CLASSES:
            raise ValueError(f"unknown DBaaS class: {self.infra_class!r}")
        if self.basis not in DBAAS_BASES:
            raise ValueError(f"unknown DBaaS basis: {self.basis!r}")
        return f"dbaas_{self.infra_class}_{self.basis}"


@dataclass
class DbaasCollection:
    quotes: list[DbaasQuote]
    html: str | None = None
    cleaned: str = ""
    extra_files: dict[str, str] = field(default_factory=dict)


Collector = Callable[[SourceConfig], DbaasCollection]


def _quote_payload(quotes: list[DbaasQuote]) -> list[dict]:
    return [
        {
            "plan_name": q.plan_name,
            "product_family": q.product_family,
            "vcpu": q.vcpu,
            "ram_gb": str(q.ram_gb),
            "disk_gb": str(q.disk_gb),
            "price_toman": str(q.price_toman),
            "provider_tier_raw": q.provider_tier_raw,
            "region": q.region,
            "pricing_type": q.pricing_type,
            "disk_type": q.disk_type,
        }
        for q in quotes
    ]


def collection_content_hash(quotes: list[DbaasQuote]) -> str:
    return content_hash(_quote_payload(quotes))


def save_dbaas_evidence(
    root: Path, provider: str, content_hash: str, collection: DbaasCollection,
) -> Path:
    files = dict(collection.extra_files)
    if collection.html is not None:
        files["rendered.html"] = collection.html
    if collection.cleaned:
        files["cleaned.md"] = collection.cleaned
    files["quotes.json"] = json.dumps(
        [asdict(q) for q in collection.quotes], ensure_ascii=False, indent=2, default=str
    )
    return write_evidence(root, provider, "dbaas", content_hash, files)


def run_dbaas_collection(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    collector: Collector,
    evidence_root: Path = EVIDENCE_ROOT,
    force: bool = False,
) -> CollectionOutcome:
    """Collect one DBaaS source end-to-end. Failures are returned, not raised."""
    provider_id, source_id, run_id = start_collection(repo, provider, source)
    outcome = CollectionOutcome(source_id=source.id, status="failed")

    try:
        collection = collector(source)
        if not collection.quotes:
            raise FetchError(f"no accepted DBaaS quotes for {source.id}")
        content_hash = collection_content_hash(collection.quotes)
        benchmarks = load_benchmarks().dbaas
        config_hash = collection_fingerprint(
            DBAAS_SCHEMA_VERSION, source.model_dump(), benchmarks.model_dump()
        )
        evidence_dir = save_dbaas_evidence(
            evidence_root, provider.slug, content_hash, collection
        )

        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(
                run_id, "success", http_status=None,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model="", schema_version=DBAAS_SCHEMA_VERSION,
            )
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        for quote in collection.quotes:
            offering_id = repo.ensure_offering(
                provider_id, source.service_type, quote.plan_name,
                product_family=quote.product_family,
                provider_tier_raw=quote.provider_tier_raw,
                region=quote.region,
            )
            raw, normalized = raw_and_normalized(quote, source.url, disk_type=quote.disk_type)
            repo.record_observation(
                run_id, offering_id, raw, normalized, evidence=quote.evidence
            )

        repo.publish_run(
            run_id, "success", http_status=None,
            content_hash=content_hash, extractor_config_hash=config_hash,
            evidence_path=str(evidence_dir), model="", schema_version=DBAAS_SCHEMA_VERSION,
        )
        outcome.status = "success"
        outcome.observations = len(collection.quotes)
        outcome.detail = {
            "quotes": len(collection.quotes),
            "classes": sorted({quote.infra_class for quote in collection.quotes}),
        }
        return outcome

    except Exception as exc:
        return fail_collection(
            repo, run_id, outcome, exc, model="", schema_version=DBAAS_SCHEMA_VERSION,
            evidence_path=str(evidence_dir) if "evidence_dir" in locals() else None,
        )


def rate_quotes(
    rates: dict[str, Decimal],
    *,
    infra_class: str,
    provider_tier_raw: str,
    region: str,
    plan_prefix: str,
    disk_type: str,
    note_for: Callable[[str, object], list[str]] | None = None,
) -> list[DbaasQuote]:
    """Build one calculated quote per configured DBaaS reference size."""
    sizes = load_benchmarks().dbaas.sizes
    if not sizes:
        raise FetchError("benchmarks.yaml defines no dbaas.sizes")
    quotes: list[DbaasQuote] = []
    for key, size in sizes.items():
        price = (
            Decimal(size.vcpu) * rates["cpu"]
            + Decimal(size.ram_gb) * rates["ram"]
            + Decimal(size.disk_gb) * rates["storage"]
        )
        quotes.append(
            DbaasQuote(
                plan_name=f"پیکربندی {plan_prefix} {size.vcpu} vCPU + {size.ram_gb} GB RAM",
                infra_class=infra_class,
                vcpu=size.vcpu,
                ram_gb=Decimal(size.ram_gb),
                disk_gb=Decimal(size.disk_gb),
                price_toman=price,
                price_raw=f"{format_toman(price, False)} تومان (محاسبه‌شده)",
                provider_tier_raw=provider_tier_raw,
                region=region,
                pricing_type="configurable_quote",
                disk_type=disk_type,
                evidence=(
                    f"{plan_prefix}: {size.vcpu}×{format_toman(rates['cpu'], False)} + "
                    f"{size.ram_gb}×{format_toman(rates['ram'], False)} + "
                    f"{size.disk_gb}×{format_toman(rates['storage'], False)} = "
                    f"{format_toman(price, False)} تومان/ماه"
                ),
                notes=note_for(key, size) if note_for else [],
            )
        )
    return quotes
