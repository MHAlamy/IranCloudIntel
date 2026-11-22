"""ArvanCloud DBaaS monthly resource rates and calculated quotes.

The DBaaS page publishes monthly per-resource rates, not fixed database
bundles. Class A uses the Premium CPU/RAM rates with local disk; Class B uses
the Standard rates with network SSD. Rates are Toman per month.
"""
from __future__ import annotations

from decimal import Decimal

from bs4 import BeautifulSoup

from collectors.arvan_fetch import fetch_with_browser
from collectors.common import FetchError
from collectors.dbaas_pipeline import DbaasCollection, DbaasQuote, rate_quotes
from config.loader import SourceConfig
from normalization.persian import parse_price
from util.format import format_toman

TIERS = ("starter", "basic", "standard", "premium")
SECTION_IDS = ("pricing-package-0", "pricing-package-1", "pricing-package-2")
BASE_NOTE = "محاسبه‌شده از نرخ‌های PAYG رسمی؛ بدون IPv4، ترافیک و بکاپ (هر دو رایگان/اختیاری)"


def _rows(section) -> dict[str, Decimal]:
    """(label, monthly amount) pairs inside one pricing accordion section."""
    rows: dict[str, Decimal] = {}
    for element in section.find_all("div"):
        cells = element.find_all("div", recursive=False)
        if len(cells) != 2:
            continue
        label = cells[0].get_text(" ", strip=True)
        amount_text = cells[1].get_text(" ", strip=True)
        if "تومان" not in amount_text:
            continue
        try:
            amount = parse_price(amount_text)
        except ValueError:
            continue
        rows.setdefault(label, amount)
    return rows


def parse_arvan_dbaas_rates(page_html: str) -> dict[str, dict[str, Decimal]]:
    soup = BeautifulSoup(page_html, "html.parser")
    sections = [soup.find(id=section_id) for section_id in SECTION_IDS]
    if any(section is None for section in sections):
        raise FetchError("Arvan DBaaS pricing accordion not found")

    cpu = {
        label.lower(): amount for label, amount in _rows(sections[0]).items()
        if label.lower() in TIERS
    }
    ram = {
        label.lower(): amount for label, amount in _rows(sections[1]).items()
        if label.lower() in TIERS
    }
    storage: dict[str, Decimal] = {}
    for label, amount in _rows(sections[2]).items():
        if "HDD" in label:
            storage["hdd"] = amount
        elif "لوکال" in label:
            storage["local"] = amount
        elif "SSD" in label:
            storage["ssd"] = amount

    missing = [f"cpu.{tier}" for tier in TIERS if tier not in cpu]
    missing += [f"ram.{tier}" for tier in TIERS if tier not in ram]
    missing += [f"storage.{kind}" for kind in ("hdd", "ssd", "local") if kind not in storage]
    if missing:
        raise FetchError(f"Arvan DBaaS rates missing: {missing}")
    return {"cpu": cpu, "ram": ram, "storage": storage}


def arvan_dbaas_quotes(rates: dict[str, dict[str, Decimal]]) -> list[DbaasQuote]:
    """Class A = Premium + local disk; Class B = Standard + network SSD."""
    classes = {
        "local": ("premium", "local", "premium_local", "پرمیوم/لوکال", "دیسک لوکال"),
        "shared": ("standard", "ssd", "standard_network", "استاندارد/شبکه", "دیسک SSD شبکه‌ای"),
    }
    quotes: list[DbaasQuote] = []
    for infra_class, (tier, disk, tier_raw, prefix, disk_label) in classes.items():
        quotes += rate_quotes(
            {
                "cpu": rates["cpu"][tier],
                "ram": rates["ram"][tier],
                "storage": rates["storage"][disk],
            },
            infra_class=infra_class,
            provider_tier_raw=tier_raw,
            region="ir-thr-ba1",
            plan_prefix=prefix,
            disk_type=disk_label,
            note_for=lambda key, size: [BASE_NOTE],
        )
    return quotes


def _cleaned_markdown(rates, quotes) -> str:
    lines = [
        "# ArvanCloud DBaaS monthly PAYG resource rates",
        "",
        "| resource | tier/disk | monthly Toman |",
        "| --- | --- | --- |",
    ]
    for tier in TIERS:
        lines.append(f"| CPU | {tier} | {format_toman(rates['cpu'][tier], False)} |")
        lines.append(f"| RAM | {tier} | {format_toman(rates['ram'][tier], False)} |")
    for disk in ("hdd", "ssd", "local"):
        lines.append(f"| Disk | {disk} | {format_toman(rates['storage'][disk], False)} |")
    lines += [
        "",
        "## Calculated reference sizes",
        "",
        "| class | vCPU | RAM GB | disk GB | monthly Toman |",
        "| --- | --- | --- | --- | --- |",
    ]
    for quote in quotes:
        lines.append(
            f"| {quote.infra_class} | {quote.vcpu} | {quote.ram_gb} | "
            f"{quote.disk_gb} | {format_toman(quote.price_toman, False)} |"
        )
    return "\n".join(lines) + "\n"


def collect_arvan_dbaas(source: SourceConfig) -> DbaasCollection:
    result = fetch_with_browser(
        source.url,
        ready_marker=source.navigation.get("ready_marker", "هر vCore"),
    )
    rates = parse_arvan_dbaas_rates(result.html)
    quotes = arvan_dbaas_quotes(rates)
    return DbaasCollection(
        quotes=quotes,
        html=result.html,
        cleaned=_cleaned_markdown(rates, quotes),
    )
