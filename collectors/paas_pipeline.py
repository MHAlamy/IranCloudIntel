"""PaaS/CNAP collection pipeline.

PaaS data is compute-shaped (vCPU/RAM/SSD), so it reuses the existing
VM-shaped `price_observations` table with `service_type='paas'`. Collection is
deterministic: published plans (Liara silver) are parsed from the page;
resource-rate providers (Hamravesh, Arvan) are calculated from their published
monthly rates. No LLM is used for this service.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from collectors.common import (
    CollectionOutcome,
    FetchError,
    fail_collection,
    start_collection,
)
from config.loader import ProviderConfig, SourceConfig, load_benchmarks
from extractors.schema import LLMPlanRow, NormalizedPlanRow
from storage.repository import Repository
from util.fingerprint import collection_fingerprint
from util.format import format_toman

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = ROOT / "evidence"
PAAS_SCHEMA_VERSION = "paas-v1"


@dataclass
class PaasQuote:
    """One comparable PaaS quote for a reference compute selection."""

    plan_name: str
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    price_toman: Decimal
    price_raw: str
    provider_tier_raw: str
    region: str
    product_family: str  # paas_fixed | paas_calculated
    pricing_type: str  # fixed_bundle | configurable_quote
    evidence: str
    notes: list[str] = field(default_factory=list)


@dataclass
class PaasCollection:
    quotes: list[PaasQuote]
    html: str | None = None
    cleaned: str = ""
    extra_files: dict[str, str] = field(default_factory=dict)


Collector = Callable[[SourceConfig], PaasCollection]


def _quote_payload(quotes: list[PaasQuote]) -> list[dict]:
    return [
        {
            "plan_name": q.plan_name,
            "vcpu": q.vcpu,
            "ram_gb": str(q.ram_gb),
            "disk_gb": str(q.disk_gb),
            "price_toman": str(q.price_toman),
            "provider_tier_raw": q.provider_tier_raw,
            "region": q.region,
            "product_family": q.product_family,
            "pricing_type": q.pricing_type,
        }
        for q in quotes
    ]


def collection_content_hash(quotes: list[PaasQuote]) -> str:
    payload = json.dumps(_quote_payload(quotes), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_paas_evidence(
    root: Path, provider: str, content_hash: str, collection: PaasCollection,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / provider / "paas" / f"{stamp}_{content_hash[:12]}"
    directory.mkdir(parents=True, exist_ok=False)
    if collection.html is not None:
        (directory / "rendered.html").write_text(collection.html, encoding="utf-8")
    if collection.cleaned:
        (directory / "cleaned.md").write_text(collection.cleaned, encoding="utf-8")
    for name, text in collection.extra_files.items():
        (directory / name).write_text(text, encoding="utf-8")
    (directory / "quotes.json").write_text(
        json.dumps([asdict(q) for q in collection.quotes], ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return directory


def _raw_and_normalized(quote: PaasQuote, source_url: str) -> tuple[LLMPlanRow, NormalizedPlanRow]:
    raw = LLMPlanRow(
        plan_name=quote.plan_name,
        provider_tier_raw=quote.provider_tier_raw,
        region=quote.region,
        vcpu=quote.vcpu,
        ram_gb=float(quote.ram_gb),
        disk_gb=float(quote.disk_gb),
        disk_type="SSD",
        price_raw=quote.price_raw,
        currency_raw="تومان",
        billing_period_raw="ماهانه",
        evidence=quote.evidence,
    )
    normalized = NormalizedPlanRow(
        plan_name=quote.plan_name,
        provider_tier_raw=quote.provider_tier_raw,
        region=quote.region,
        vcpu=quote.vcpu,
        ram_gb=float(quote.ram_gb),
        disk_gb=float(quote.disk_gb),
        disk_type="SSD",
        price_value=quote.price_toman,
        currency="toman",
        price_in_toman=quote.price_toman,
        billing_period="monthly",
        pricing_type=quote.pricing_type,
        plan_url=source_url,
        validation_status="valid",
        validation_issues=[],
    )
    return raw, normalized


def run_paas_collection(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    collector: Collector,
    evidence_root: Path = EVIDENCE_ROOT,
    force: bool = False,
) -> CollectionOutcome:
    """Collect one PaaS source end-to-end. Failures are returned, not raised."""
    provider_id, source_id, run_id = start_collection(repo, provider, source)
    outcome = CollectionOutcome(source_id=source.id, status="failed")

    try:
        collection = collector(source)
        if not collection.quotes:
            raise FetchError(f"no accepted PaaS quotes for {source.id}")
        content_hash = collection_content_hash(collection.quotes)
        benchmarks = load_benchmarks().paas
        config_hash = collection_fingerprint(
            PAAS_SCHEMA_VERSION, source.model_dump(), benchmarks.model_dump()
        )
        evidence_dir = save_paas_evidence(
            evidence_root, provider.slug, content_hash, collection
        )

        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(
                run_id, "success", http_status=None,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model="", schema_version=PAAS_SCHEMA_VERSION,
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
            raw, normalized = _raw_and_normalized(quote, source.url)
            repo.record_observation(
                run_id, offering_id, raw, normalized, evidence=quote.evidence
            )

        repo.publish_run(
            run_id, "success", http_status=None,
            content_hash=content_hash, extractor_config_hash=config_hash,
            evidence_path=str(evidence_dir), model="", schema_version=PAAS_SCHEMA_VERSION,
        )
        outcome.status = "success"
        outcome.observations = len(collection.quotes)
        outcome.detail = {
            "quotes": len(collection.quotes),
            "tier": collection.quotes[0].provider_tier_raw,
        }
        return outcome

    except Exception as exc:
        return fail_collection(
            repo, run_id, outcome, exc, model="", schema_version=PAAS_SCHEMA_VERSION,
            evidence_path=str(evidence_dir) if "evidence_dir" in locals() else None,
        )


def calculated_price(rates: dict[str, Decimal], selection) -> Decimal:
    return (
        Decimal(selection.vcpu) * rates["cpu"]
        + Decimal(selection.ram_gb) * rates["ram"]
        + Decimal(selection.disk_gb) * rates["storage"]
    )


def rate_quotes(
    rates: dict[str, Decimal],
    *,
    provider_tier_raw: str,
    region: str,
    product_family: str,
    pricing_type: str,
    plan_prefix: str,
    note_for: Callable[[str, object], list[str]] | None = None,
) -> list[PaasQuote]:
    """Build one calculated quote per configured PaaS selection."""
    selections = load_benchmarks().paas.selections
    if not selections:
        raise FetchError("benchmarks.yaml defines no paas.selections")
    quotes: list[PaasQuote] = []
    for key, selection in selections.items():
        price = calculated_price(rates, selection)
        notes = note_for(key, selection) if note_for else []
        quotes.append(
            PaasQuote(
                plan_name=f"پیکربندی {selection.vcpu} vCPU + {selection.ram_gb} GB RAM",
                vcpu=selection.vcpu,
                ram_gb=Decimal(selection.ram_gb),
                disk_gb=Decimal(selection.disk_gb),
                price_toman=price,
                price_raw=f"{format_toman(price, False)} تومان (محاسبه‌شده)",
                provider_tier_raw=provider_tier_raw,
                region=region,
                product_family=product_family,
                pricing_type=pricing_type,
                evidence=(
                    f"{plan_prefix}: {selection.vcpu}×{format_toman(rates['cpu'], False)} + "
                    f"{selection.ram_gb}×{format_toman(rates['ram'], False)} + "
                    f"{selection.disk_gb}×{format_toman(rates['storage'], False)} = "
                    f"{format_toman(price, False)} تومان/ماه"
                ),
                notes=notes,
            )
        )
    return quotes
