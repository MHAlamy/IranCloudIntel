"""Offline (manual) price-list import pipeline.

A transcribed document cannot be fetched, so acquisition is replaced by a
deterministic loader that reads a versioned dataset package
(`datasets/offline/<source_id>/`). Everything after loading follows the same
path as the network collectors: validated observations are appended to
`price_observations` and the run is published atomically.

The run stores the source document and its validity, so the dashboard can
distinguish manually imported prices from automatically collected ones.
No LLM is used: the dataset is already structured.
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

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = ROOT / "evidence"
OFFLINE_SCHEMA_VERSION = "offline-vm-v1"
OFFLINE_RATES_SCHEMA_VERSION = "offline-os-rates-v1"


@dataclass
class OfflinePlan:
    """One comparable plan derived from an offline price document."""

    plan_name: str
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    price_toman: Decimal
    price_raw: str
    provider_tier_raw: str
    region: str
    product_family: str
    pricing_type: str
    evidence: str
    disk_type: str | None = None


@dataclass
class OfflineCollection:
    plans: list[OfflinePlan]
    source_document: str
    valid_until: str | None = None
    cleaned: str = ""
    extra_files: dict[str, str] = field(default_factory=dict)


@dataclass
class OfflineOsRate:
    """One Object Storage PAYG rate derived from an offline document."""

    category: str  # storage | traffic | requests | feature
    unit: str
    tier_label: str
    range_label: str
    range_min_gb: str | None
    range_max_gb: str | None
    amount_toman: str | None  # None when is_free
    is_free: bool
    evidence: str
    region: str = "iran"


@dataclass
class OfflineRateCollection:
    rates: list[OfflineOsRate]
    source_document: str
    valid_until: str | None = None
    cleaned: str = ""
    extra_files: dict[str, str] = field(default_factory=dict)


Loader = Callable[[SourceConfig], OfflineCollection]
RatesLoader = Callable[[SourceConfig], OfflineRateCollection]


def _plan_payload(plans: list[OfflinePlan]) -> list[dict]:
    return [
        {
            "plan_name": p.plan_name,
            "vcpu": p.vcpu,
            "ram_gb": str(p.ram_gb),
            "disk_gb": str(p.disk_gb),
            "price_toman": str(p.price_toman),
            "provider_tier_raw": p.provider_tier_raw,
            "region": p.region,
            "product_family": p.product_family,
        }
        for p in plans
    ]


def collection_content_hash(plans: list[OfflinePlan]) -> str:
    return content_hash(_plan_payload(plans))


def save_offline_evidence(
    root: Path, provider: str, service: str, content_hash: str,
    collection: OfflineCollection,
) -> Path:
    files = {name: text for name, text in collection.extra_files.items() if text}
    if collection.cleaned:
        files["cleaned.md"] = collection.cleaned
    files["plans.json"] = json.dumps(
        [asdict(p) for p in collection.plans], ensure_ascii=False, indent=2, default=str
    )
    return write_evidence(root, provider, f"{service}_offline", content_hash, files)


def save_offline_rate_evidence(
    root: Path, provider: str, service: str, content_hash: str,
    collection: OfflineRateCollection,
) -> Path:
    files = {name: text for name, text in collection.extra_files.items() if text}
    if collection.cleaned:
        files["cleaned.md"] = collection.cleaned
    files["rates.json"] = json.dumps(
        [asdict(r) for r in collection.rates], ensure_ascii=False, indent=2, default=str
    )
    return write_evidence(root, provider, f"{service}_offline", content_hash, files)


def run_offline_collection(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    loader: Loader,
    evidence_root: Path = EVIDENCE_ROOT,
    force: bool = False,
) -> CollectionOutcome:
    """Import one manual source end-to-end. Failures are returned, not raised."""
    provider_id, source_id, run_id = start_collection(repo, provider, source)
    outcome = CollectionOutcome(source_id=source.id, status="failed")

    try:
        collection = loader(source)
        if not collection.plans:
            raise FetchError(f"no accepted plans in {source.url}")
        content_hash = collection_content_hash(collection.plans)
        config_hash = collection_fingerprint(
            OFFLINE_SCHEMA_VERSION,
            source.model_dump(),
            {"vm_sizes": {k: v.model_dump() for k, v in load_benchmarks().vm.sizes.items()}},
        )
        evidence_dir = save_offline_evidence(
            evidence_root, provider.slug, source.service_type, content_hash, collection
        )

        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(
                run_id, "success", http_status=None,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model="", schema_version=OFFLINE_SCHEMA_VERSION,
                source_document=collection.source_document,
                valid_until=collection.valid_until,
            )
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        for plan in collection.plans:
            offering_id = repo.ensure_offering(
                provider_id, source.service_type, plan.plan_name,
                product_family=plan.product_family,
                provider_tier_raw=plan.provider_tier_raw,
                region=plan.region,
            )
            raw, normalized = raw_and_normalized(plan, source.url, disk_type=plan.disk_type)
            repo.record_observation(
                run_id, offering_id, raw, normalized, evidence=plan.evidence
            )

        repo.publish_run(
            run_id, "success", http_status=None,
            content_hash=content_hash, extractor_config_hash=config_hash,
            evidence_path=str(evidence_dir), model="", schema_version=OFFLINE_SCHEMA_VERSION,
            source_document=collection.source_document,
            valid_until=collection.valid_until,
        )
        outcome.status = "success"
        outcome.observations = len(collection.plans)
        outcome.detail = {
            "plans": len(collection.plans),
            "source_document": collection.source_document,
            "valid_until": collection.valid_until,
        }
        return outcome

    except Exception as exc:
        return fail_collection(
            repo, run_id, outcome, exc, model="", schema_version=OFFLINE_SCHEMA_VERSION,
            evidence_path=str(evidence_dir) if "evidence_dir" in locals() else None,
        )


def _rate_payload(rates: list[OfflineOsRate]) -> list[dict]:
    return [
        {
            "category": r.category,
            "unit": r.unit,
            "tier_label": r.tier_label,
            "range_label": r.range_label,
            "range_min_gb": r.range_min_gb,
            "range_max_gb": r.range_max_gb,
            "amount_toman": r.amount_toman,
            "is_free": r.is_free,
            "region": r.region,
        }
        for r in rates
    ]


def rates_content_hash(rates: list[OfflineOsRate]) -> str:
    return content_hash(_rate_payload(rates))


def run_offline_rates_collection(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    loader: RatesLoader,
    evidence_root: Path = EVIDENCE_ROOT,
    force: bool = False,
) -> CollectionOutcome:
    """Import one manual rate-table source (Object Storage PAYG) end-to-end."""
    provider_id, source_id, run_id = start_collection(repo, provider, source)
    outcome = CollectionOutcome(source_id=source.id, status="failed")

    try:
        collection = loader(source)
        if not collection.rates:
            raise FetchError(f"no accepted rates in {source.url}")
        content_hash = rates_content_hash(collection.rates)
        config_hash = collection_fingerprint(
            OFFLINE_RATES_SCHEMA_VERSION, source.model_dump()
        )
        evidence_dir = save_offline_rate_evidence(
            evidence_root, provider.slug, source.service_type, content_hash, collection
        )

        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(
                run_id, "success", http_status=None,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model="",
                schema_version=OFFLINE_RATES_SCHEMA_VERSION,
                source_document=collection.source_document,
                valid_until=collection.valid_until,
            )
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        repo.record_os_rates(run_id, provider_id, collection.rates)

        repo.publish_run(
            run_id, "success", http_status=None,
            content_hash=content_hash, extractor_config_hash=config_hash,
            evidence_path=str(evidence_dir), model="",
            schema_version=OFFLINE_RATES_SCHEMA_VERSION,
            source_document=collection.source_document,
            valid_until=collection.valid_until,
        )
        outcome.status = "success"
        outcome.observations = len(collection.rates)
        outcome.detail = {
            "rates": len(collection.rates),
            "source_document": collection.source_document,
            "valid_until": collection.valid_until,
        }
        return outcome

    except Exception as exc:
        return fail_collection(
            repo, run_id, outcome, exc, model="",
            schema_version=OFFLINE_RATES_SCHEMA_VERSION,
            evidence_path=str(evidence_dir) if "evidence_dir" in locals() else None,
        )
