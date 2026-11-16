"""ParsPack cloud-storage collection: drive the interactive calculator and
record storage-only monthly quotes.

Fourth collection mode variant (configurable_quote, like the VM collector):
the provider's own calculator is the source and there are no published
bundles. The calculator prices storage only (disk type HDD/SSD × location
ایران/اروپا × period), so observations carry no traffic allowance — the
no-traffic caveat is recorded at dashboard level (app/data.py).

Owner-relevant selection (2026-11-16): HDD, ایران, ۱ ماهه — one month periods
without SSD pricing or multi-period discounts.

Interaction notes (probed 2026-11-16):
- the page is fully JS-rendered and `networkidle` never settles; navigate with
  `domcontentloaded` + a fixed settle delay;
- radios must be activated via JS `click()` — Playwright's label click times
  out (the labels are not the radio's accessible labels);
- the capacity slider is `disabled` until a disk type / location / period is
  chosen, then accepts keyboard arrows; the framework resets JS property
  writes, so the value is walked step by step with ArrowRight from Home.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from util.fingerprint import collection_fingerprint
from collectors.arvan_clean import sha256_text  # noqa: E402
from collectors.pipeline import CollectionOutcome  # noqa: E402
from config.loader import ProviderConfig, SourceConfig  # noqa: E402
from extractors.os_schema import LLMStoragePlanRow  # noqa: E402
from normalization.os_validate import normalize_os_row  # noqa: E402
from storage.repository import Repository  # noqa: E402

# Deterministic starting state of the calculator (owner-selected options).
DISK_TYPE = "hdd"
LOCATION = "iran"
PERIOD = "monthly"

_CONFIG_HASH = "parspack-os-quote-v1"

_ACTIVATE_RADIO = """(val) => {
    const el = document.querySelector(`input[type=radio][value=${val}]`);
    if (el) { el.click(); el.dispatchEvent(new Event('input', {bubbles: true})); }
    return el ? el.checked : null;
}"""

# Persian digits -> the quote's numeric fields, tolerant of ٬/٬ thousand marks.
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _to_int(text: str) -> int:
    return int(text.strip().translate(_DIGITS).replace("٬", "").replace(",", ""))


def read_quote(page) -> tuple[int, int] | None:
    """Read (storage_gb, monthly_toman) from the calculator's current state.

    The GB label is a standalone line (e.g. «۲٬۰۰۰ GB»); the monthly price is
    the number on the line right after «ماهیانه» in the جمع کل block.
    """
    lines = [ln.strip() for ln in page.inner_text("body").split("\n") if ln.strip()]
    storage_gb = None
    for ln in lines:
        match = re.match(r"^([\d۰-۹,٬]+)\s*GB$", ln)
        if match:
            storage_gb = _to_int(match.group(1))
            break
    monthly = None
    for i, ln in enumerate(lines):
        if ln == "ماهیانه" or ln.startswith("ماهیانه"):
            for candidate in lines[i + 1:i + 3]:
                if re.fullmatch(r"[\d۰-۹,٬]+", candidate):
                    monthly = _to_int(candidate)
                    break
            break
    if storage_gb is None or monthly is None:
        return None
    return storage_gb, monthly


def collect_storage_quotes(page) -> list[dict]:
    """Walk the slider across its full scale and quote every stop."""
    for value in (DISK_TYPE, LOCATION, PERIOD):
        checked = page.evaluate(_ACTIVATE_RADIO, value)
        if not checked:
            raise RuntimeError(f"ParsPack storage radio {value!r} not found/activatable")
        page.wait_for_timeout(400)

    slider = page.locator("input[type=range]").first
    slider.evaluate("e => e.focus()")
    page.wait_for_timeout(300)
    max_pos = int(slider.evaluate("e => e.max"))
    page.keyboard.press("Home")
    page.wait_for_timeout(400)

    quotes: list[dict] = []
    for position in range(0, max_pos + 1):
        current = int(slider.input_value())
        for _ in range(position - current):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(120)
        page.wait_for_timeout(700)
        read = read_quote(page)
        if read is None:
            raise RuntimeError(f"ParsPack storage quote unreadable at slider position {position}")
        storage_gb, monthly = read
        quotes.append({
            "position": position,
            "storage_gb": storage_gb,
            "monthly_toman": str(monthly),
        })
    return quotes


def quotes_markdown(quotes: list[dict], source_url: str) -> str:
    """Cleaned quote table (evidence + content-hash input)."""
    lines = [
        "# ParsPack cloud-storage calculator quotes",
        f"Source: {source_url}",
        f"Selection: disk=HDD, location=ایران, period=۱ ماهه (monthly)",
        "",
        "| position | storage (GB) | monthly (تومان) |",
        "| --- | --- | --- |",
    ]
    for quote in quotes:
        lines.append(
            f"| {quote['position']} | {quote['storage_gb']} | {quote['monthly_toman']} |"
        )
    lines += [
        "",
        "ترافیک در ماشین‌حساب قیمت‌گذاری نمی‌شود؛ فقط حجم ذخیره‌سازی.",
    ]
    return "\n".join(lines) + "\n"


def run_parspack_os(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    evidence_root: Path,
    force: bool = False,
) -> CollectionOutcome:
    """Collect ParsPack storage calculator quotes as object-storage observations."""
    outcome = CollectionOutcome(source_id=source.id, status="failed")
    provider_id = repo.ensure_provider(provider.slug, provider.name, provider.official_url)
    source_id = repo.ensure_source(
        provider_id, source.service_type, source.url, source.collection_method, source.region_scope
    )
    run_id = repo.start_run(source_id)
    try:
        from playwright.sync_api import sync_playwright

        from collectors.browser import launch_browser

        with sync_playwright() as p:
            browser = launch_browser(p)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
                page.goto(source.url, wait_until="domcontentloaded", timeout=90_000)
                page.wait_for_timeout(8_000)
                quotes = collect_storage_quotes(page)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                cleaned = quotes_markdown(quotes, source.url)
                content_hash = sha256_text(cleaned)
                evidence_dir = evidence_root / provider.slug / source.service_type / f"{stamp}_{content_hash[:12]}"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                (evidence_dir / "rendered.html").write_text(page.content(), encoding="utf-8")
                (evidence_dir / "cleaned.md").write_text(cleaned, encoding="utf-8")
                (evidence_dir / "quotes.json").write_text(
                    json.dumps(quotes, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            finally:
                browser.close()

        config_hash = collection_fingerprint(_CONFIG_HASH, source.model_dump())
        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(
                run_id, "success", http_status=200, content_hash=content_hash,
                extractor_config_hash=config_hash, evidence_path=str(evidence_dir),
            )
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        observations = 0
        for quote in quotes:
            plan_name = f"فضای ابری HDD {_format_fa(quote['storage_gb'])} گیگابایت"
            raw = LLMStoragePlanRow(
                plan_name=plan_name,
                price_raw=f"{quote['monthly_toman']} تومان",
                currency_raw="تومان",
                billing_period_raw="ماهانه",
                storage_raw=f"{quote['storage_gb']} گیگابایت",
                traffic_raw=None,           # calculator prices storage only
                requests_raw=None,
                unlimited_raw=None,
                evidence=(
                    f"ماشین‌حساب پارس‌پک (HDD، ایران، ۱ ماهه): "
                    f"ماهیانه {quote['monthly_toman']} تومان برای {quote['storage_gb']} GB"
                ),
            )
            normalized = normalize_os_row(raw, plan_url=source.url)
            if normalized.validation_status != "valid":
                raise RuntimeError(
                    f"ParsPack storage quote failed validation: {normalized.validation_issues}"
                )
            offering_id = repo.ensure_offering(
                provider_id, source.service_type, normalized.plan_name,
                product_family="calculator_quote", provider_tier_raw="hdd", region="iran",
            )
            repo.record_os_observation(
                run_id, offering_id, normalized,
                price_raw=raw.price_raw,
                currency_raw=raw.currency_raw,
                billing_period_raw=raw.billing_period_raw,
                evidence=raw.evidence,
            )
            observations += 1

        repo.publish_run(
            run_id, "success", http_status=200, content_hash=content_hash,
            extractor_config_hash=config_hash, evidence_path=str(evidence_dir),
        )
        outcome.status = "success"
        outcome.observations = observations
        return outcome
    except Exception as exc:
        repo.publish_run(run_id, "failed", error=str(exc)[:2000])
        outcome.error = str(exc)
        return outcome


def _format_fa(number: int) -> str:
    """1000 -> '۱٬۰۰۰' for a human-readable plan name."""
    latin = f"{number:,}".replace(",", "٬")
    return latin.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
