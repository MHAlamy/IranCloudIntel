"""KaaS tariff collection pipeline.

KaaS prices are component-shaped (per-vCPU, per-GB, management-fee tiers), so
they reuse `resource_rates` instead of the single-price `price_observations`
table. Scenario totals are calculated later by `comparison.kaas_pricing`, which
keeps pricing rules out of the view layer.

Fee rows use `category='management_fee'` and a half-open ladder label such as
`0-200`; providers whose top band is quote-only simply stop before that band.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from collectors.common import (
    CollectionOutcome,
    FetchError,
    content_hash,
    fail_collection,
    start_collection,
    write_evidence,
)
from config.loader import ProviderConfig, SourceConfig, load_benchmarks
from storage.repository import Repository
from util.fingerprint import collection_fingerprint

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = ROOT / "evidence"
KAAS_SCHEMA_VERSION = "kaas-rates-v1"


@dataclass
class KaasRate:
    """One component or management-fee row from a provider's KaaS pricing."""

    category: str  # cpu | ram | storage | management_fee
    unit: str
    tier_label: str
    amount_toman: str
    evidence: str
    region: str = "iran"


@dataclass
class KaasCollection:
    rates: list[KaasRate]
    html: str | None = None
    cleaned: str = ""
    source_document: str = ""
    valid_until: str | None = None
    extra_files: dict[str, str] = field(default_factory=dict)


Collector = Callable[[SourceConfig], KaasCollection]


def _rate_payload(rates: list[KaasRate]) -> list[dict]:
    return [
        {
            "category": rate.category,
            "unit": rate.unit,
            "tier_label": rate.tier_label,
            "amount_toman": rate.amount_toman,
            "region": rate.region,
        }
        for rate in rates
    ]


def collection_content_hash(rates: list[KaasRate]) -> str:
    return content_hash(_rate_payload(rates))


def save_kaas_evidence(
    root: Path, provider: str, content_hash_value: str, collection: KaasCollection,
) -> Path:
    files = dict(collection.extra_files)
    if collection.html is not None:
        files["rendered.html"] = collection.html
    if collection.cleaned:
        files["cleaned.md"] = collection.cleaned
    files["rates.json"] = json.dumps(
        [asdict(rate) for rate in collection.rates],
        ensure_ascii=False,
        indent=2,
    )
    return write_evidence(root, provider, "kaas", content_hash_value, files)


def run_kaas_collection(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    collector: Collector,
    evidence_root: Path = EVIDENCE_ROOT,
    force: bool = False,
) -> CollectionOutcome:
    """Collect one KaaS source end-to-end. Failures are returned, not raised."""
    provider_id, source_id, run_id = start_collection(repo, provider, source)
    outcome = CollectionOutcome(source_id=source.id, status="failed")

    try:
        collection = collector(source)
        if not collection.rates:
            raise FetchError(f"no accepted KaaS tariffs for {source.id}")
        digest = collection_content_hash(collection.rates)
        config_hash = collection_fingerprint(
            KAAS_SCHEMA_VERSION, source.model_dump(), load_benchmarks().kaas.model_dump()
        )
        evidence_dir = save_kaas_evidence(
            evidence_root, provider.slug, digest, collection
        )

        if not force and repo.should_skip_extraction(source_id, digest, config_hash):
            repo.publish_run(
                run_id, "success", http_status=None,
                content_hash=digest, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model="", schema_version=KAAS_SCHEMA_VERSION,
                source_document=collection.source_document or None,
                valid_until=collection.valid_until,
            )
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        repo.record_rates(run_id, provider_id, collection.rates)
        repo.publish_run(
            run_id, "success", http_status=None,
            content_hash=digest, extractor_config_hash=config_hash,
            evidence_path=str(evidence_dir), model="", schema_version=KAAS_SCHEMA_VERSION,
            source_document=collection.source_document or None,
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
            repo, run_id, outcome, exc, model="", schema_version=KAAS_SCHEMA_VERSION,
            evidence_path=str(evidence_dir) if "evidence_dir" in locals() else None,
        )
