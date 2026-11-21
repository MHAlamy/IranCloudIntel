"""Shared collector records and evidence lifecycle helpers."""
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from extractors.schema import LLMPlanRow, NormalizedPlanRow


class FetchError(RuntimeError):
    pass


@dataclass
class FetchResult:
    html: str
    http_status: int | None
    final_url: str


@dataclass
class CollectionOutcome:
    source_id: str
    status: str  # success | failed
    skipped: bool = False
    observations: int = 0
    suspect_rows: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    detail: dict = field(default_factory=dict)


def write_evidence(root: Path, provider: str, folder: str, content_hash: str,
                   files: dict[str, str]) -> Path:
    """Write one timestamped evidence directory; callers choose the files."""
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory = root / provider / folder / f'{stamp}_{content_hash[:12]}'
    directory.mkdir(parents=True, exist_ok=False)
    for name, text in files.items():
        (directory / name).write_text(text, encoding='utf-8')
    return directory


def save_evidence(root: Path, provider: str, service: str, content_hash: str,
                  html: str, cleaned: str) -> Path:
    return write_evidence(
        root, provider, service, content_hash,
        {'rendered.html': html, 'cleaned.md': cleaned},
    )


def content_hash(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def raw_and_normalized(plan, source_url: str, disk_type: str | None = None):
    """Build the raw/normalized pair shared by PaaS and offline imports."""
    raw = LLMPlanRow(
        plan_name=plan.plan_name,
        provider_tier_raw=plan.provider_tier_raw,
        region=plan.region,
        vcpu=plan.vcpu,
        ram_gb=float(plan.ram_gb),
        disk_gb=float(plan.disk_gb),
        disk_type=disk_type,
        price_raw=plan.price_raw,
        currency_raw='تومان',
        billing_period_raw='ماهانه',
        evidence=plan.evidence,
    )
    normalized = NormalizedPlanRow(
        plan_name=plan.plan_name,
        provider_tier_raw=plan.provider_tier_raw,
        region=plan.region,
        vcpu=plan.vcpu,
        ram_gb=float(plan.ram_gb),
        disk_gb=float(plan.disk_gb),
        disk_type=disk_type,
        price_value=plan.price_toman,
        currency='toman',
        price_in_toman=plan.price_toman,
        billing_period='monthly',
        pricing_type=plan.pricing_type,
        plan_url=source_url,
        validation_status='valid',
        validation_issues=[],
    )
    return raw, normalized


def start_collection(repo, provider, source):
    """Register source identity and persist an attempt before acquisition."""
    provider_id = repo.ensure_provider(provider.slug, provider.name, provider.official_url)
    source_id = repo.ensure_source(provider_id, source.service_type, source.url,
                                   source.collection_method, source.region_scope)
    return provider_id, source_id, repo.start_run(source_id)


def fail_collection(repo, run_id, outcome, exc, **metadata):
    """Record failure without exposing staged prices; keep available evidence."""
    repo.publish_run(run_id, 'failed', error=str(exc)[:2000], **metadata)
    outcome.error = str(exc)
    return outcome


def current_model() -> str:
    import os
    return os.getenv("AIaaS_MODEL", "")
