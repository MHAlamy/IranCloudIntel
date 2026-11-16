"""Liara PaaS (silver tier) published plans.

The pricing page renders all tiers client-side; the collector selects the
middle «نقره‌ای» tier and reads the PaaS plan cards. Only published plans are
recorded; Liara has no 32 vCPU + 64 GB silver plan, so that reference is left
for Hamravesh and Arvan.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bs4 import BeautifulSoup

from collectors.arvan_fetch import fetch_with_browser
from collectors.common import FetchError
from collectors.paas_pipeline import PaasCollection, PaasQuote
from config.loader import SourceConfig, load_benchmarks
from normalization.persian import parse_price
from util.format import format_toman


@dataclass
class LiaraPaasPlan:
    plan_name: str
    monthly_toman: Decimal
    hourly_toman: Decimal
    ram_gb: Decimal
    vcpu: Decimal
    disk_gb: Decimal
    raw_text: str


def parse_liara_paas_cards(cards: list[str]) -> list[LiaraPaasPlan]:
    """Parse card texts in display order: name, monthly, hourly, RAM, vCPU, disk."""
    plans: list[LiaraPaasPlan] = []
    for text in cards:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 6:
            continue
        numbers: list[Decimal] = []
        for line in lines[1:]:
            if not any(ch.isdigit() for ch in line):
                continue
            try:
                numbers.append(parse_price(line))
            except ValueError:
                continue
        if len(numbers) < 5:
            continue
        monthly, hourly, ram, vcpu, disk = numbers[:5]
        plans.append(
            LiaraPaasPlan(
                plan_name=lines[0],
                monthly_toman=monthly,
                hourly_toman=hourly,
                ram_gb=ram,
                vcpu=vcpu,
                disk_gb=disk,
                raw_text=" | ".join(lines),
            )
        )
    return plans


def extract_liara_paas_cards(page_html: str) -> list[str]:
    """Card texts from the active silver PaaS tier container.

    After selection the active tier button loses its data-gtm attributes, so
    the active state is read from the tier group itself; the PaaS group is
    anchored by its stable «پایه» button.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    basic = soup.find(
        "button",
        attrs={"data-gtm-position": "paas", "data-gtm-label": "پایه"},
    )
    if basic is None:
        raise FetchError("Liara PaaS tier group not found")
    tier_group = basic.parent
    active = tier_group.find("button", class_="active") if tier_group else None
    if active is None or "نقره" not in active.get_text(" ", strip=True):
        raise FetchError("Liara PaaS silver tier was not selected")

    container = tier_group
    items = []
    for _ in range(8):
        container = container.parent
        if container is None:
            break
        items = container.find_all("div", class_="item")
        if len(items) >= 7:
            break
    if len(items) < 7:
        raise FetchError("Liara PaaS silver plan cards not found")
    return [item.get_text("\n", strip=True) for item in items[:7]]


def liara_quotes_from_plans(
    plans: list[LiaraPaasPlan], tier_label: str = "نقره‌ای",
) -> list[PaasQuote]:
    """Map published silver plans onto the configured reference selections."""
    by_resources = {
        (plan.vcpu, plan.ram_gb, plan.disk_gb): plan for plan in plans
    }
    quotes: list[PaasQuote] = []
    for selection in load_benchmarks().paas.selections.values():
        key = (Decimal(selection.vcpu), Decimal(selection.ram_gb), Decimal(selection.disk_gb))
        plan = by_resources.get(key)
        if plan is None:
            continue
        quotes.append(
            PaasQuote(
                plan_name=plan.plan_name,
                vcpu=selection.vcpu,
                ram_gb=Decimal(selection.ram_gb),
                disk_gb=Decimal(selection.disk_gb),
                price_toman=plan.monthly_toman,
                price_raw=f"{format_toman(plan.monthly_toman, False)} تومان",
                provider_tier_raw=tier_label,
                region="ir-iran",
                product_family="paas_fixed",
                pricing_type="fixed_bundle",
                evidence=f"Liara PaaS silver plan {plan.plan_name}: {plan.raw_text}",
                notes=["پلن منتشرشده‌ی لیارا در سطح نقرهای"],
            )
        )
    return quotes


def collect_liara_paas(source: SourceConfig) -> PaasCollection:
    navigation = source.navigation
    tier_label = navigation.get("tier_label", "نقره‌ای")
    result = fetch_with_browser(
        source.url,
        ready_marker=navigation.get("ready_marker", "۹۵۰,۰۰۰"),
        click_selector=navigation.get("click_selector"),
    )
    plans = parse_liara_paas_cards(extract_liara_paas_cards(result.html))
    quotes = liara_quotes_from_plans(plans, tier_label)
    if not quotes:
        raise FetchError("no matching Liara silver PaaS plans found")
    lines = [
        "# Liara PaaS silver plans",
        "",
        "| plan | vCPU | RAM GB | SSD GB | monthly Toman |",
        "| --- | --- | --- | --- | --- |",
    ]
    for plan in plans:
        lines.append(
            f"| {plan.plan_name} | {plan.vcpu} | {plan.ram_gb} | {plan.disk_gb} | "
            f"{format_toman(plan.monthly_toman, False)} |"
        )
    return PaasCollection(
        quotes=quotes,
        html=result.html,
        cleaned="\n".join(lines) + "\n",
    )
