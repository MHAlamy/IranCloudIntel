"""Liara DBaaS (silver tier) published plans.

The pricing page renders the DBaaS cards client-side. The same planet-named
cards are used for PaaS and DBaaS, so card extraction and parsing are reused;
only the reference-size mapping differs. Class B compares the published silver
plans directly.
"""
from __future__ import annotations

from decimal import Decimal

from collectors.arvan_fetch import fetch_with_browser
from collectors.common import FetchError
from collectors.dbaas_pipeline import DbaasCollection, DbaasQuote
from collectors.liara_paas import (
    LiaraPaasPlan,
    extract_liara_paas_cards,
    parse_liara_paas_cards,
)
from config.loader import SourceConfig, load_benchmarks
from util.format import format_toman


def liara_dbaas_quotes_from_plans(
    plans: list[LiaraPaasPlan], tier_label: str = "نقره‌ای",
) -> list[DbaasQuote]:
    """Map published silver DBaaS plans onto the configured reference sizes."""
    by_resources = {
        (plan.vcpu, plan.ram_gb, plan.disk_gb): plan for plan in plans
    }
    quotes: list[DbaasQuote] = []
    for size in load_benchmarks().dbaas.sizes.values():
        key = (Decimal(size.vcpu), Decimal(size.ram_gb), Decimal(size.disk_gb))
        plan = by_resources.get(key)
        if plan is None:
            continue
        quotes.append(
            DbaasQuote(
                plan_name=plan.plan_name,
                infra_class="shared",
                vcpu=size.vcpu,
                ram_gb=Decimal(size.ram_gb),
                disk_gb=Decimal(size.disk_gb),
                price_toman=plan.monthly_toman,
                price_raw=f"{format_toman(plan.monthly_toman, False)} تومان",
                provider_tier_raw=tier_label,
                region="ir-iran",
                pricing_type="fixed_bundle",
                disk_type="SSD",
                basis="published",
                evidence=f"Liara DBaaS silver plan {plan.plan_name}: {plan.raw_text}",
                notes=["پلن منتشرشده‌ی لیارا در سطح نقره‌ای"],
            )
        )
    return quotes


def _cleaned_markdown(plans: list[LiaraPaasPlan], quotes: list[DbaasQuote]) -> str:
    lines = [
        "# Liara DBaaS silver plans",
        "",
        "| plan | vCPU | RAM GB | SSD GB | monthly Toman |",
        "| --- | --- | --- | --- | --- |",
    ]
    for plan in plans:
        lines.append(
            f"| {plan.plan_name} | {plan.vcpu} | {plan.ram_gb} | {plan.disk_gb} | "
            f"{format_toman(plan.monthly_toman, False)} |"
        )
    lines += ["", "## Reference matches", ""]
    for quote in quotes:
        lines.append(
            f"- {quote.plan_name}: {quote.vcpu} vCPU, {quote.ram_gb} GB RAM, "
            f"{quote.disk_gb} GB SSD = {format_toman(quote.price_toman, False)} Toman"
        )
    return "\n".join(lines) + "\n"


def collect_liara_dbaas(source: SourceConfig) -> DbaasCollection:
    navigation = source.navigation
    tier_label = navigation.get("tier_label", "نقره‌ای")
    result = fetch_with_browser(
        source.url,
        ready_marker=navigation.get("ready_marker", "۹۵۰,۰۰۰"),
        click_selector=navigation.get("click_selector"),
    )
    plans = parse_liara_paas_cards(
        extract_liara_paas_cards(result.html, position="dbaas")
    )
    quotes = liara_dbaas_quotes_from_plans(plans, tier_label)
    if not quotes:
        raise FetchError("no matching Liara silver DBaaS plans found")
    return DbaasCollection(
        quotes=quotes,
        html=result.html,
        cleaned=_cleaned_markdown(plans, quotes),
    )
