"""Shared collector records and evidence lifecycle helpers."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

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


def save_evidence(root: Path, provider: str, service: str, content_hash: str,
                  html: str, cleaned: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory = root / provider / service / f'{stamp}_{content_hash[:12]}'
    directory.mkdir(parents=True, exist_ok=False)
    (directory / 'rendered.html').write_text(html, encoding='utf-8')
    (directory / 'cleaned.md').write_text(cleaned, encoding='utf-8')
    return directory


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
