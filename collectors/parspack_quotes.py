"""ParsPack cloud-server collection: drive the interactive calculator and
quote the owner's baseline configurations.

This is a third collection mode (configurable_quote): no published bundles,
no rate table — the provider's own calculator is the source. Prices are
quoted daily; the comparable monthly price applies the owner-approved
adjustments from config/analyst_facts.yaml (5% monthly discount, fixed
IPv4 price added).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


from util.fingerprint import collection_fingerprint
from collectors.arvan_clean import sha256_text  # noqa: E402
from collectors.waits import wait_until
from collectors.common import start_collection, fail_collection, CollectionOutcome, FetchError  # noqa: E402
from config.loader import AnalystProviderFacts, ProviderConfig, SourceConfig  # noqa: E402
from extractors.schema import LLMPlanRow, NormalizedPlanRow  # noqa: E402
from storage.repository import Repository  # noqa: E402

# Discovered calculator scales (probed 2026-11-15)
RAM_SCALE = [2, 4, 8, 16, 32, 64]           # slider position = index
DISK_MIN, DISK_STEP = 25, 5                 # 25 GB + 5 GB per position
CPU_LINEAR_MAX = 16                          # positions 0..15 → 1..16 cores; 16 → 32


def nearest_ram_position(ram_gb: int) -> int:
    return min(range(len(RAM_SCALE)), key=lambda i: abs(RAM_SCALE[i] - ram_gb))


def nearest_disk_position(disk_gb: int) -> int:
    return max(0, round((disk_gb - DISK_MIN) / DISK_STEP))


def nearest_cpu_position(cores: int) -> int:
    if cores >= 32:
        return 16
    return max(0, min(15, cores - 1))


def compute_monthly(daily: Decimal, facts: AnalystProviderFacts) -> Decimal:
    """Comparable monthly price: daily x month_days x discount + IPv4."""
    monthly = daily * facts.month_days * facts.monthly_discount
    if facts.ipv4_monthly_toman is not None:
        monthly += facts.ipv4_monthly_toman
    return monthly


def collect_quotes(page, configs: list[dict]) -> list[dict]:
    """Drive the calculator for each baseline config; return actual quotes."""
    sliders = page.locator("input[type=range]").all()
    if len(sliders) < 3:
        raise FetchError("ParsPack calculator sliders not found")

    def set_slider(slider, value):
        slider.evaluate(
            "(e, v) => { const proto = Object.getPrototypeOf(e); const setter = "
            "Object.getOwnPropertyDescriptor(proto, 'value').set; setter.call(e, String(v)); "
            "e.dispatchEvent(new Event('input', {bubbles: true})); "
            "e.dispatchEvent(new Event('change', {bubbles: true})); }",
            value,
        )
        wait_until(page, lambda: slider.input_value() == str(value), "VM slider value")

    def read_currents():
        widget_text = sliders[0].evaluate(
            "e => { let n = e; for (let i = 0; i < 8 && n.parentElement; i++) n = n.parentElement; return n.innerText; }"
        )
        import re
        lines = [ln.strip() for ln in widget_text.split("\n") if ln.strip()]
        currents = {}
        for i, ln in enumerate(lines):
            if ln == "رم" and i + 2 < len(lines):
                currents["ram"] = lines[i + 2]
            elif ln == "فضا" and i + 2 < len(lines):
                currents["disk"] = lines[i + 2]
            elif ln == "پردازنده" and i + 2 < len(lines):
                currents["cpu"] = lines[i + 2]
        return currents

    def read_daily():
        import re
        body = page.inner_text("body")
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        price_line = re.compile(r"^[۰-۹0-9٬,]+ تومان$")
        for i, ln in enumerate(lines):
            if ln == "روزانه:" and i + 1 < len(lines) and price_line.match(lines[i + 1]):
                return lines[i + 1]
        raise FetchError("ParsPack daily quote line not found")

    quotes = []
    for config in configs:
        before = read_currents()
        try:
            previous_daily = read_daily()
        except FetchError:
            previous_daily = None
        set_slider(sliders[0], nearest_ram_position(config["ram"]))
        set_slider(sliders[1], nearest_disk_position(config["disk"]))
        set_slider(sliders[2], nearest_cpu_position(config["cpu"]))
        expected = dict(ram=f"{RAM_SCALE[nearest_ram_position(config['ram'])]}GB",
                        disk=f"{DISK_MIN + DISK_STEP * nearest_disk_position(config['disk'])}GB",
                        cpu=f"{32 if config['cpu'] >= 32 else config['cpu']} Core")
        def ready_quote():
            currents = read_currents()
            if any(currents.get(key, '').replace(' ', '') != value.replace(' ', '') for key, value in expected.items()):
                return None
            try:
                daily = read_daily()
            except FetchError:
                return None
            unchanged = all(before.get(key, "").replace(" ", "") == value.replace(" ", "") for key, value in expected.items())
            return (currents, daily) if unchanged or previous_daily is None or daily != previous_daily else None
        currents, daily_text = wait_until(page, ready_quote, "VM resource labels and updated price")
        previous_daily = daily_text
        daily = Decimal(str(daily_text)
                        .replace("تومان", "").strip()
                        .translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
                        .replace("٬", "").replace(",", ""))
        quotes.append({
            "label": config["label"],
            "cpu": int(currents.get("cpu", "").replace(" Core", "")),
            "ram_gb": int(currents.get("ram", "").replace("GB", "")),
            "disk_gb": int(currents.get("disk", "").replace("GB", "")),
            "daily_text": daily_text,
            "daily_toman": str(daily),
        })
    return quotes


def run_parspack_quotes(
    provider: ProviderConfig,
    source: SourceConfig,
    repo: Repository,
    facts: AnalystProviderFacts,
    evidence_root: Path,
    force: bool = False,
) -> CollectionOutcome:
    """Collect ParsPack calculator quotes for the baseline configs."""
    outcome = CollectionOutcome(source_id=source.id, status="failed")
    provider_id, source_id, run_id = start_collection(repo, provider, source)
    try:
        from datetime import datetime, timezone
        from collectors.browser import launch_browser
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = launch_browser(p)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900}, locale="fa-IR")
                page.goto(source.url, wait_until="domcontentloaded", timeout=60_000)
                page.locator("input[type=range]").first.wait_for(state="visible", timeout=60000)
                # deterministic starting state: Iran, Tehran11, Ubuntu
                try:
                    page.locator("select").nth(0).select_option(label="ایران")
                    page.wait_for_function("() => document.querySelector('select')?.selectedOptions[0]?.label === \u0027\u0627\u06cc\u0631\u0627\u0646\u0027")
                except Exception as exc:
                    raise FetchError("cannot confirm Iranian calculator region") from exc
                quotes = collect_quotes(page, [q.model_dump() for q in facts.quotes])
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                content_hash = sha256_text(json.dumps(quotes, sort_keys=True))
                evidence_dir = evidence_root / provider.slug / source.service_type / f"{stamp}_{content_hash[:12]}"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                (evidence_dir / "quotes.json").write_text(
                    json.dumps(quotes, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            finally:
                browser.close()

        config_hash = collection_fingerprint("parspack-quote-v1", facts.model_dump(), source.model_dump())
        if not force and repo.should_skip_extraction(source_id, content_hash, config_hash):
            repo.publish_run(run_id, "success", http_status=200, content_hash=content_hash,
                            extractor_config_hash=config_hash, evidence_path=str(evidence_dir))
            outcome.status = "success"
            outcome.skipped = True
            return outcome

        observations = 0
        for quote in quotes:
            daily = Decimal(quote["daily_toman"])
            monthly = compute_monthly(daily, facts)
            offering_id = repo.ensure_offering(
                provider_id, source.service_type,
                f"{quote['cpu']}vCPU-{quote['ram_gb']}GB-{quote['disk_gb']}GB",
                product_family="calculator_quote", provider_tier_raw="standard",
                region="ir-tehran11",
            )
            raw = LLMPlanRow(
                plan_name=f"{quote['cpu']}vCPU-{quote['ram_gb']}GB-{quote['disk_gb']}GB",
                provider_tier_raw="standard", region="ir-tehran11",
                vcpu=quote["cpu"], ram_gb=float(quote["ram_gb"]), disk_gb=float(quote["disk_gb"]),
                disk_type=None,
                price_raw=quote["daily_text"], currency_raw="تومان",
                billing_period_raw="روزانه",
                evidence=f"ParsPack calculator quote ({quote['label']}): {quote['daily_text']}/day, "
                         f"config {quote['cpu']} Core/{quote['ram_gb']}GB/{quote['disk_gb']}GB",
            )
            normalized = NormalizedPlanRow(
                plan_name=raw.plan_name, provider_tier_raw="standard", region="ir-tehran11",
                vcpu=quote["cpu"], ram_gb=Decimal(quote["ram_gb"]), disk_gb=Decimal(quote["disk_gb"]),
                disk_type=None,
                price_value=monthly, currency="toman", price_in_toman=monthly,
                billing_period="monthly", pricing_type="configurable_quote",
                plan_url=source.url,
                validation_status="valid", validation_issues=[],
            )
            repo.record_observation(run_id, offering_id, raw, normalized)
            observations += 1

        repo.publish_run(run_id, "success", http_status=200, content_hash=content_hash,
                        extractor_config_hash=config_hash, evidence_path=str(evidence_dir))
        outcome.status = "success"
        outcome.observations = observations
        return outcome
    except Exception as exc:
        return fail_collection(repo, run_id, outcome, exc, evidence_path=str(evidence_dir) if 'evidence_dir' in locals() else None)
