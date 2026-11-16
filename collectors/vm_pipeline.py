"""VM collection orchestration and bundle verification."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


from util.fingerprint import collection_fingerprint
from config.loader import ProviderConfig, SourceConfig, load_benchmarks
from collectors.arvan_clean import TabContent, sha256_text
from comparison.rate_check import STORAGE_CLASS_LABELS, ProviderRateMapping, TierRates, verify_bundle
from comparison.matching import is_iranian_region
from decimal import Decimal
from extractors.llm import LLMClient, LLMError
from extractors.prompts import SYSTEM_PROMPT, build_extraction_messages
from extractors.schema import LLMPlanRow, NormalizedPlanRow, SCHEMA_VERSION
from normalization.validate import normalize_llm_row
from storage.repository import Repository

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = ROOT / "evidence"


from collectors.common import start_collection, fail_collection, FetchError, FetchResult, CollectionOutcome, save_evidence

Cleaner = Callable[[str, str, tuple[str, ...]], dict[str, TabContent]]
Fetcher = Callable[[SourceConfig], FetchResult]


from collectors.common import current_model as _current_model

def extractor_config_hash(model: str) -> str:
    """Hash of everything that defines extraction behavior; a change forces re-extraction."""
    payload = json.dumps(
        {"model": model, "schema_version": SCHEMA_VERSION, "system_prompt": SYSTEM_PROMPT},
        sort_keys=True,
    )
    return collection_fingerprint(payload)


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
    plans_parser: Callable[[str], list] | None = None,
) -> CollectionOutcome:
    """Collect one source end-to-end. Raises nothing; failures are returned."""
    provider_id, source_id, run_id = start_collection(repo, provider, source)
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
            config_hash = collection_fingerprint("rates", provider.slug)

        config_hash = collection_fingerprint(config_hash, source.model_dump(), rate_mappings)
        evidence_dir = save_evidence(evidence_root, provider.slug, source.service_type, content_hash, fetch_result.html, combined_markdown)

        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(
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
                rates_lookup = _tier_rates_from_repo(repo, provider_id, rate_mappings[provider.slug], run_id)

        # Deterministic-bundle providers (e.g. Liara): plans parsed directly,
        # no LLM call. Comparable price includes the provider's documented
        # IPv4 surcharge when the page states one.
        if plans_parser is not None:
            plans = plans_parser(fetch_result.html)
            from collectors.liara_plans import parse_ipv4_monthly

            ipv4_monthly = parse_ipv4_monthly(fetch_result.html)
            if ipv4_monthly is None:
                raise FetchError("Liara IPv4 surcharge unknown; comparable total cannot be published")
            recorded = 0
            for plan in plans:
                offering_id = repo.ensure_offering(
                    provider_id, source.service_type, plan.name,
                    product_family="fixed_bundle", provider_tier_raw="standard",
                    region="ir-iran",
                )
                comparable = Decimal(plan.monthly_toman)
                if ipv4_monthly is not None:
                    comparable += Decimal(ipv4_monthly)
                raw = LLMPlanRow(
                    plan_name=plan.name, provider_tier_raw="standard", region="ir-iran",
                    vcpu=int(Decimal(plan.vcpu)), ram_gb=float(Decimal(plan.ram_gb)),
                    disk_gb=float(Decimal(plan.disk_gb)), disk_type=None,
                    price_raw=plan.monthly_text, currency_raw="تومان",
                    billing_period_raw="ماهانه",
                    evidence=f"Liara IaaS bundle {plan.name}: {plan.monthly_text}/month "
                             f"({plan.vcpu} vCPU, {plan.ram_gb} GB RAM, {plan.disk_gb} GB SSD)",
                )
                normalized = NormalizedPlanRow(
                    plan_name=plan.name, provider_tier_raw="standard", region="ir-iran",
                    vcpu=int(Decimal(plan.vcpu)), ram_gb=Decimal(plan.ram_gb),
                    disk_gb=Decimal(plan.disk_gb), disk_type=None,
                    price_value=Decimal(plan.monthly_toman), currency="toman",
                    price_in_toman=comparable, billing_period="monthly",
                    pricing_type="fixed_bundle", plan_url=source.url,
                    validation_status="valid", validation_issues=[],
                )
                repo.record_observation(run_id, offering_id, raw, normalized)
                recorded += 1

            repo.publish_run(
                run_id, "success", http_status=fetch_result.http_status,
                content_hash=content_hash, extractor_config_hash=config_hash,
                evidence_path=str(evidence_dir), model=_current_model(),
                schema_version=SCHEMA_VERSION,
            )
            outcome.status = "success"
            outcome.observations = recorded
            outcome.detail = {"plans_stored": recorded, "ipv4_monthly": ipv4_monthly}
            return outcome

        # Rate-table-only sources (no published VM bundles, e.g. Kubit):
        # store rates and finish; no LLM call, no bundle observations.
        if not bundle_extraction:
            repo.publish_run(
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

                if not rows:
                    raise FetchError(f"empty extraction for tab {tab}")
                for raw_row in rows:
                    try:
                        plan_row = LLMPlanRow(**raw_row)
                    except Exception as exc:
                        review_entries.append({"tab": tab, "row": raw_row, "error": str(exc)})
                        suspect += 1
                        continue
                    normalized = normalize_llm_row(plan_row, monthly_hours=load_benchmarks().vm.monthly_hours)
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

        if observations == 0:
            raise FetchError("no accepted VM plans; review required")
        repo.publish_run(
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
        return fail_collection(repo, run_id, outcome, exc, model=_current_model(),
                               evidence_path=str(evidence_dir) if 'evidence_dir' in locals() else None,
                               prompt_tokens=locals().get('prompt_tokens', 0),
                               completion_tokens=locals().get('completion_tokens', 0))


def _tier_rates_from_repo(repo: Repository, provider_id: int, mapping: ProviderRateMapping, run_id: int | None = None):
    """Build a per-plan rate lookup from the provider's stored Iran rates.

    Returns an object with .rates_for(plan_name) -> TierRates | None, or None
    when the provider's rate table is unusable for verification.
    """
    rows = repo.latest_rates(provider_id, region="iran", staged_run_id=run_id)
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


