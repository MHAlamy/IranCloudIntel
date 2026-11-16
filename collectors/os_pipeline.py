"""Object Storage collection orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


from util.fingerprint import collection_fingerprint
from config.loader import ProviderConfig, SourceConfig
from collectors.arvan_clean import TabContent, sha256_text
from decimal import Decimal
from extractors.llm import LLMClient, LLMError
from extractors.os_prompts import OS_SYSTEM_PROMPT
from extractors.os_schema import OS_SCHEMA_VERSION
from normalization.os_validate import normalize_os_row
from normalization.persian import parse_price
from storage.repository import Repository

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = ROOT / "evidence"


from collectors.common import start_collection, fail_collection, FetchError, FetchResult, CollectionOutcome, save_evidence

Cleaner = Callable[[str, str, tuple[str, ...]], dict[str, TabContent]]
Fetcher = Callable[[SourceConfig], FetchResult]


from collectors.common import current_model as _current_model

def os_extractor_config_hash(model: str) -> str:
    """Hash of everything that defines OS extraction behavior."""
    payload = json.dumps(
        {"model": model, "schema_version": OS_SCHEMA_VERSION, "system_prompt": OS_SYSTEM_PROMPT},
        sort_keys=True,
    )
    return collection_fingerprint(payload)


def _overage_toman(raw: str | None) -> str | None:
    """'۳,۰۰۰ تومان' -> '3000'; markers like 'تماس بگیرید' -> None."""
    if not raw:
        return None
    try:
        return str(Decimal(parse_price(raw)))
    except ValueError:
        return None


def run_os_collection(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    fetcher: Fetcher,
    cleaner: Callable[[str, str], str],
    llm_factory: Callable[[], LLMClient] | None = None,
    os_plans_parser: Callable[[str], list] | None = None,
    os_rates_parser: Callable[[str], list] | None = None,
    os_crosscheck: Callable[[str, list], list[dict]] | None = None,
    tb_to_gb: int = 1024,
    evidence_root: Path = EVIDENCE_ROOT,
    force: bool = False,
) -> CollectionOutcome:
    """Collect one object-storage source end-to-end. Failures are returned."""
    provider_id, source_id, run_id = start_collection(repo, provider, source)
    outcome = CollectionOutcome(source_id=source.id, status="failed")

    try:
        fetch_result = fetcher(source)
        cleaned = cleaner(fetch_result.html, source.url)
        content_hash = sha256_text(cleaned)
        if llm_factory is not None:
            config_hash = os_extractor_config_hash(_current_model())
        else:
            config_hash = collection_fingerprint("os", provider.slug)

        config_hash = collection_fingerprint(config_hash, source.model_dump(), tb_to_gb)
        evidence_dir = save_evidence(evidence_root, provider.slug, source.service_type, content_hash, fetch_result.html, cleaned)

        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(
                run_id, "success", http_status=fetch_result.http_status,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model=_current_model(),
                schema_version=OS_SCHEMA_VERSION,
            )
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        rates_stored = 0
        if os_rates_parser is not None:
            rates_stored = repo.record_os_rates(
                run_id, provider_id, os_rates_parser(fetch_result.html)
            )

        prompt_tokens = completion_tokens = 0
        observations = suspect = 0
        review_entries: list[dict] = []

        if os_plans_parser is not None:
            # Deterministic plan parsing (e.g. Hamravesh's attribute matrix):
            # no LLM call; overage rates come from the same table.
            from collectors.hamravesh_os import OSPlan  # noqa: F401  (typing only)
            from extractors.os_schema import LLMStoragePlanRow
            from normalization.os_validate import normalize_os_row

            for plan in os_plans_parser(fetch_result.html):
                price_raw = plan.price_raw or ""
                raw = LLMStoragePlanRow(
                    plan_name=plan.plan_name,
                    price_raw=price_raw,
                    currency_raw="تومان" if "تومان" in price_raw else "",
                    billing_period_raw="ماهانه" if price_raw and "ثبت درخواست" not in price_raw else "",
                    storage_raw=plan.storage_raw,
                    traffic_raw=plan.traffic_raw,
                    requests_raw=None,
                    unlimited_raw=None,
                    evidence=plan.evidence,
                )
                normalized = normalize_os_row(raw, tb_to_gb=tb_to_gb, plan_url=source.url)
                if normalized.validation_status != "valid":
                    review_entries.append({"plan": plan.plan_name, "issues": normalized.validation_issues})
                    suspect += 1
                    continue
                offering_id = repo.ensure_offering(
                    provider_id, source.service_type, normalized.plan_name,
                    product_family="fixed_bundle", provider_tier_raw="", region="",
                )
                repo.record_os_observation(
                    run_id, offering_id, normalized,
                    price_raw=price_raw,
                    currency_raw=raw.currency_raw,
                    billing_period_raw=raw.billing_period_raw,
                    evidence=plan.evidence,
                    overage_storage_toman_gb=_overage_toman(plan.overage_storage_raw),
                    overage_traffic_toman_gb=_overage_toman(plan.overage_traffic_raw),
                )
                observations += 1
        elif llm_factory is not None:
            from extractors.os_prompts import build_os_extraction_messages
            from extractors.os_schema import LLMStoragePlanRow
            from normalization.os_validate import normalize_os_row

            context = {
                "provider": provider.name,
                "service": source.service_type,
                "source_url": source.url,
                "region_scope": source.region_scope,
            }
            with llm_factory() as client:
                messages = build_os_extraction_messages(cleaned, context=context)
                try:
                    rows, telemetry = client.extract_rows(messages)
                except LLMError as exc:
                    raise FetchError(f"OS extraction failed: {exc}") from exc
                prompt_tokens = telemetry.prompt_tokens
                completion_tokens = telemetry.completion_tokens

            normalized_pairs = []
            for raw_row in rows:
                try:
                    raw = LLMStoragePlanRow(**raw_row)
                except Exception as exc:
                    review_entries.append({"row": raw_row, "error": str(exc)})
                    suspect += 1
                    continue
                normalized = normalize_os_row(raw, tb_to_gb=tb_to_gb, plan_url=source.url)
                if normalized.validation_status != "valid":
                    review_entries.append({"row": raw_row, "issues": normalized.validation_issues})
                    suspect += 1
                    continue
                normalized_pairs.append((raw, normalized))

            # Deterministic cross-check against the page's comparison matrix
            # (review-only: mismatches are flagged, never silently accepted).
            if os_crosscheck is not None:
                review_entries.extend(os_crosscheck(fetch_result.html, normalized_pairs))

            for raw, normalized in normalized_pairs:
                offering_id = repo.ensure_offering(
                    provider_id, source.service_type, normalized.plan_name,
                    product_family="fixed_bundle", provider_tier_raw="", region="",
                )
                repo.record_os_observation(
                    run_id, offering_id, normalized,
                    price_raw=raw.price_raw,
                    currency_raw=raw.currency_raw,
                    billing_period_raw=raw.billing_period_raw,
                    evidence=raw.evidence,
                )
                observations += 1

        if review_entries:
            (evidence_dir / "review_queue.json").write_text(
                json.dumps(review_entries, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        if observations == 0:
            raise FetchError("no accepted Object Storage plans; review required")
        repo.publish_run(
            run_id, "success", http_status=fetch_result.http_status,
            content_hash=content_hash, extractor_config_hash=config_hash,
            evidence_path=str(evidence_dir), model=_current_model(),
            schema_version=OS_SCHEMA_VERSION, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        outcome.status = "success"
        outcome.observations = observations
        outcome.suspect_rows = suspect
        outcome.prompt_tokens = prompt_tokens
        outcome.completion_tokens = completion_tokens
        outcome.detail = {"rates_stored": rates_stored}
        return outcome

    except Exception as exc:
        return fail_collection(repo, run_id, outcome, exc, model=_current_model(),
                               evidence_path=str(evidence_dir) if 'evidence_dir' in locals() else None,
                               prompt_tokens=locals().get('prompt_tokens', 0),
                               completion_tokens=locals().get('completion_tokens', 0))


