"""One-shot collection pipeline: fetch -> clean -> skip-check -> extract ->
validate -> persist. No overlapping runs (RunLock is held by the CLI).

Failure behavior (PROJECT_GUIDE.md 4.2, price_gathering_guide.md 4.3):
- every attempt is recorded as a collection run;
- failures never touch existing observations;
- suspect rows are quarantined to a review file, never recorded as prices.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.loader import ProviderConfig, SourceConfig  # noqa: E402
from collectors.arvan_clean import TabContent, build_cleaned_markdown, sha256_text  # noqa: E402
from comparison.rate_check import STORAGE_CLASS_LABELS, ProviderRateMapping, TierRates, verify_bundle  # noqa: E402
from comparison.matching import is_iranian_region  # noqa: E402
from decimal import Decimal  # noqa: E402
from extractors.llm import LLMClient, LLMError  # noqa: E402
from extractors.prompts import SYSTEM_PROMPT, build_extraction_messages  # noqa: E402
from extractors.schema import LLMPlanRow, SCHEMA_VERSION  # noqa: E402
from normalization.validate import normalize_llm_row  # noqa: E402
from storage.repository import Repository  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = ROOT / "evidence"


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


Cleaner = Callable[[str, str, tuple[str, ...]], dict[str, TabContent]]
Fetcher = Callable[[SourceConfig], FetchResult]


def extractor_config_hash(model: str) -> str:
    """Hash of everything that defines extraction behavior; a change forces re-extraction."""
    payload = json.dumps(
        {"model": model, "schema_version": SCHEMA_VERSION, "system_prompt": SYSTEM_PROMPT},
        sort_keys=True,
    )
    return sha256_text(payload)


def run_collection(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    llm_factory: Callable[[], LLMClient],
    fetcher: Fetcher,
    cleaner: Cleaner,
    evidence_root: Path = EVIDENCE_ROOT,
    force: bool = False,
    rates_parser: Callable[[str], list] | None = None,
    rate_mappings: dict | None = None,
    bundle_extraction: bool = True,
) -> CollectionOutcome:
    """Collect one source end-to-end. Raises nothing; failures are returned."""
    provider_id = repo.ensure_provider(provider.slug, provider.name, provider.official_url)
    source_id = repo.ensure_source(
        provider_id, source.service_type, source.url, source.collection_method, source.region_scope
    )
    run_id = repo.start_run(source_id)
    outcome = CollectionOutcome(source_id=source.id, status="failed")

    try:
        tabs: tuple[str, ...] = tuple(source.navigation.get("tabs", ()))
        if not tabs:
            raise FetchError(f"source {source.id} defines no tabs to collect")

        fetch_result = fetcher(source)
        cleaned = cleaner(fetch_result.html, source.url, tabs)
        combined_markdown = "\n\n".join(cleaned[tab].markdown for tab in tabs)
        content_hash = sha256_text(combined_markdown)
        if bundle_extraction:
            config_hash = extractor_config_hash(_current_model())
        else:
            # rates-only sources: the "extractor" is the deterministic rate parser
            config_hash = sha256_text(f"rates-parser:{provider.slug}")

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        evidence_dir = evidence_root / provider.slug / source.service_type / f"{stamp}_{content_hash[:12]}"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "rendered.html").write_text(fetch_result.html, encoding="utf-8")
        (evidence_dir / "cleaned.md").write_text(combined_markdown, encoding="utf-8")

        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.finish_run(
                run_id, "success", http_status=fetch_result.http_status,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model=_current_model(),
                schema_version=SCHEMA_VERSION,
            )
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        # Component rate tables (providers that publish them, e.g. Arvan, Kubit):
        # parsed deterministically from the same rendered page, stored for the run.
        rates_stored = 0
        rates_lookup = None
        if rates_parser is not None:
            rates_stored = repo.record_rates(run_id, provider_id, rates_parser(fetch_result.html))
            if rate_mappings and provider.slug in rate_mappings:
                rates_lookup = _tier_rates_from_repo(repo, provider_id, rate_mappings[provider.slug])

        # Rate-table-only sources (no published VM bundles, e.g. Kubit):
        # store rates and finish; no LLM call, no bundle observations.
        if not bundle_extraction:
            repo.finish_run(
                run_id, "success", http_status=fetch_result.http_status,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model=_current_model(),
                schema_version=SCHEMA_VERSION,
            )
            outcome.status = "success"
            outcome.skipped = False
            outcome.detail = {"rates_stored": rates_stored}
            return outcome

        prompt_tokens = completion_tokens = 0
        observations = suspect = 0
        review_entries: list[dict] = []
        with llm_factory() as client:
            for tab in tabs:
                tab_content = cleaned[tab]
                context = {
                    "provider": provider.name,
                    "service": source.service_type,
                    "tab": tab,
                    "source_url": source.url,
                    "region_scope": source.region_scope,
                }
                messages = build_extraction_messages(tab_content.markdown, context=context)
                try:
                    rows, telemetry = client.extract_rows(messages)
                except LLMError as exc:
                    raise FetchError(f"extraction failed for tab {tab!r}: {exc}") from exc
                prompt_tokens += telemetry.prompt_tokens
                completion_tokens += telemetry.completion_tokens

                for raw_row in rows:
                    try:
                        plan_row = LLMPlanRow(**raw_row)
                    except Exception as exc:
                        review_entries.append({"tab": tab, "row": raw_row, "error": str(exc)})
                        suspect += 1
                        continue
                    normalized = normalize_llm_row(plan_row)
                    if normalized.validation_status != "valid":
                        review_entries.append(
                            {"tab": tab, "row": raw_row, "issues": normalized.validation_issues}
                        )
                        suspect += 1
                        continue
                    offering_id = repo.ensure_offering(
                        provider_id, source.service_type, normalized.plan_name,
                        product_family="", provider_tier_raw=normalized.provider_tier_raw,
                        region=normalized.region or "",
                    )
                    latest_observation_id = repo.record_observation(
                        run_id, offering_id, plan_row, normalized, evidence=plan_row.evidence
                    )
                    observations += 1

                    # Bundle-vs-rates verification (deterministic, zero tokens)
                    if rate_mappings and provider.slug in rate_mappings and rates_stored:
                        mapping = rate_mappings[provider.slug]
                        tier_rates = rates_lookup.rates_for(normalized.plan_name)
                        if not is_iranian_region(normalized.region or ""):
                            status, detail = (
                                "review", "non-Iranian region; not verified against Iranian rates"
                            )
                        elif tier_rates is not None and normalized.vcpu is not None:
                            status, detail = verify_bundle(
                                normalized.plan_name, normalized.vcpu,
                                Decimal(str(normalized.ram_gb)), Decimal(str(normalized.disk_gb)),
                                normalized.price_in_toman, tier_rates, mapping,
                            )
                        else:
                            status, detail = "review", "rates or resources incomplete for verification"
                        repo.set_rate_verification(latest_observation_id, status, detail)

        if review_entries:
            (evidence_dir / "review_queue.json").write_text(
                json.dumps(review_entries, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        repo.finish_run(
            run_id, "success", http_status=fetch_result.http_status,
            content_hash=content_hash, extractor_config_hash=config_hash,
            evidence_path=str(evidence_dir), model=_current_model(),
            schema_version=SCHEMA_VERSION, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        outcome.status = "success"
        outcome.observations = observations
        outcome.suspect_rows = suspect
        outcome.prompt_tokens = prompt_tokens
        outcome.completion_tokens = completion_tokens
        return outcome

    except Exception as exc:
        repo.finish_run(run_id, "failed", error=str(exc)[:2000], model=_current_model())
        outcome.error = str(exc)
        return outcome


def _current_model() -> str:
    import os

    return os.getenv("AIaaS_MODEL", "")


def _tier_rates_from_repo(repo: Repository, provider_id: int, mapping: ProviderRateMapping):
    """Build a per-plan rate lookup from the provider's stored Iran rates.

    Returns an object with .rates_for(plan_name) -> TierRates | None, or None
    when the provider's rate table is unusable for verification.
    """
    rows = repo.latest_rates(provider_id, region="iran")
    by_key = {(r["category"], r["unit"], r["tier_label"]): r for r in rows}
    ipv4_row = next((r for (cat, _, label), r in by_key.items() if cat == "ipv4" and "اول" in label), None)
    if ipv4_row is None:
        return None

    tier_labels = {"basic": "Basic", "standard": "Standard", "premium": "Premium"}
    cache: dict[tuple[str, str], TierRates] = {}

    def build(tier_label: str, storage_label: str) -> TierRates | None:
        key = (tier_label, storage_label)
        if key in cache:
            return cache[key]
        cpu = by_key.get(("cpu", "هر vCore", tier_label))
        ram = by_key.get(("ram", "هر گیگابایت", tier_label))
        storage = by_key.get(("storage", "هر گیگابایت", storage_label))
        if cpu is None or ram is None or storage is None:
            return None
        rates = TierRates(
            cpu_rate=Decimal(cpu["amount_toman"]),
            ram_rate=Decimal(ram["amount_toman"]),
            storage_rate=Decimal(storage["amount_toman"]),
            ipv4_first=Decimal(ipv4_row["amount_toman"]),
        )
        cache[key] = rates
        return rates

    class _Lookup:
        def rates_for(self, plan_name: str) -> TierRates | None:
            family = mapping.family_for(plan_name)
            if family is None:
                return None
            return build(tier_labels[family["rate_tier"]], STORAGE_CLASS_LABELS[family["storage_class"]])

    return _Lookup()


def fetch_source(source: SourceConfig) -> FetchResult:
    """Dispatch fetching by collection method (browser for JS/challenge sites,
    plain HTTP for static pages)."""
    if source.collection_method == "playwright":
        from collectors.arvan_fetch import fetch_with_browser

        marker = source.navigation.get("ready_marker", "")
        result = fetch_with_browser(source.url, ready_marker=marker)
        return FetchResult(html=result.html, http_status=result.http_status, final_url=result.final_url)
    if source.collection_method == "http":
        import httpx

        response = httpx.get(
            source.url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                "Accept-Language": "fa,en;q=0.8",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        response.raise_for_status()
        return FetchResult(html=response.text, http_status=response.status_code, final_url=str(response.url))
    raise FetchError(f"collection method {source.collection_method!r} not implemented yet")
