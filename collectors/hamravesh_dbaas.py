"""Hamravesh managed database monthly resource rates and calculated quotes.

The pricing page publishes two plans side by side: unmanaged (عادی) and managed
(مدیریت‌شده). DBaaS is compared on the managed monthly rates; Class A uses
those rates with SSD storage. The page states prices are for a 30-day month.
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

MANAGED_NOTE = (
    "نرخ پلن مدیریت‌شده؛ صفحه فقط «SSD» اعلام کرده و محلی بودن دیسک تأیید نشده است"
)
BASE_NOTE = "ماه ۳۰ روزه (۷۲۰ ساعت)؛ بدون ترافیک و IPv4"


def parse_hamravesh_dbaas_rates(page_html: str) -> dict[str, Decimal]:
    """Managed monthly rates from the (label, hourly, monthly, hourly, monthly) rows."""
    soup = BeautifulSoup(page_html, "html.parser")
    rates: dict[str, Decimal] = {}
    markers = {
        "cpu": "vCore",
        "ram": "GB رم",
        "storage": "SSD",
    }
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) != 5:
                continue
            label = cells[0]
            for key, marker in markers.items():
                if key in rates or marker not in label:
                    continue
                try:
                    # columns: label, unmanaged hourly/monthly, managed hourly/monthly
                    rates[key] = parse_price(cells[4])
                except ValueError:
                    continue
        if len(rates) == 3:
            break
    missing = {"cpu", "ram", "storage"} - set(rates)
    if missing:
        raise FetchError(f"Hamravesh DBaaS managed rates missing: {sorted(missing)}")
    return rates


def hamravesh_dbaas_quotes(rates: dict[str, Decimal]) -> list[DbaasQuote]:
    return rate_quotes(
        rates,
        infra_class="local",
        provider_tier_raw="managed",
        region="ir-iran",
        plan_prefix="مدیریت‌شده",
        disk_type="SSD",
        note_for=lambda key, size: [MANAGED_NOTE, BASE_NOTE],
    )


def _cleaned_markdown(rates: dict[str, Decimal], quotes) -> str:
    lines = [
        "# Hamravesh managed DBaaS monthly resource rates (Iran datacenter)",
        "",
        "| resource | monthly Toman |",
        "| --- | --- |",
        f"| vCore | {format_toman(rates['cpu'], False)} |",
        f"| RAM GB | {format_toman(rates['ram'], False)} |",
        f"| SSD GB | {format_toman(rates['storage'], False)} |",
        "",
        "## Calculated reference sizes",
        "",
        "| class | vCPU | RAM GB | SSD GB | monthly Toman |",
        "| --- | --- | --- | --- | --- |",
    ]
    for quote in quotes:
        lines.append(
            f"| {quote.infra_class} | {quote.vcpu} | {quote.ram_gb} | "
            f"{quote.disk_gb} | {format_toman(quote.price_toman, False)} |"
        )
    return "\n".join(lines) + "\n"


def collect_hamravesh_dbaas(source: SourceConfig) -> DbaasCollection:
    navigation = source.navigation
    result = fetch_with_browser(
        source.url,
        ready_marker=navigation.get("ready_marker", "هر vCore پردازنده"),
        click_selector=navigation.get("click_selector"),
    )
    rates = parse_hamravesh_dbaas_rates(result.html)
    quotes = hamravesh_dbaas_quotes(rates)
    return DbaasCollection(
        quotes=quotes,
        html=result.html,
        cleaned=_cleaned_markdown(rates, quotes),
    )
