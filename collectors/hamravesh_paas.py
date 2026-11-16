"""Hamravesh Darakub (PaaS) monthly resource rates and calculated quotes."""
from __future__ import annotations

from decimal import Decimal

from bs4 import BeautifulSoup

from collectors.arvan_fetch import fetch_with_browser
from collectors.common import FetchError
from collectors.paas_pipeline import PaasCollection, rate_quotes
from config.loader import SourceConfig
from normalization.persian import parse_price
from util.format import format_toman

IRAN_NOTE = "محاسبه‌شده از نرخ‌های دیتاسنتر ایران؛ بدون ترافیک، IPv4 و مانیتورینگ"


def parse_hamravesh_paas_rates(page_html: str) -> dict[str, Decimal]:
    """First (Iran) occurrence of the three monthly resource rates."""
    soup = BeautifulSoup(page_html, "html.parser")
    rates: dict[str, Decimal] = {}
    labels = {
        "cpu": "هر vCore",
        "ram": "هر GB رم",
        "storage": "SSD",
    }
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            # The live table also carries a composite summary row; only the
            # clean (label, hourly, monthly) rows are usable.
            if len(cells) != 3:
                continue
            label = cells[0]
            for key, marker in labels.items():
                if key in rates or marker not in label:
                    continue
                try:
                    rates[key] = parse_price(cells[2])
                except ValueError:
                    continue
        if len(rates) == 3:
            break
    missing = {"cpu", "ram", "storage"} - set(rates)
    if missing:
        raise FetchError(f"Hamravesh Darakub rates missing: {sorted(missing)}")
    return rates


def _cleaned_markdown(rates: dict[str, Decimal], quotes) -> str:
    lines = [
        "# Hamravesh Darakub (Iran datacenter) monthly resource rates",
        "",
        "| resource | monthly Toman |",
        "| --- | --- |",
        f"| vCore | {format_toman(rates['cpu'], False)} |",
        f"| RAM GB | {format_toman(rates['ram'], False)} |",
        f"| SSD GB | {format_toman(rates['storage'], False)} |",
        "",
        "## Calculated reference selections",
        "",
        "| vCPU | RAM GB | SSD GB | monthly Toman |",
        "| --- | --- | --- | --- |",
    ]
    for quote in quotes:
        lines.append(
            f"| {quote.vcpu} | {quote.ram_gb} | {quote.disk_gb} | "
            f"{format_toman(quote.price_toman, False)} |"
        )
    return "\n".join(lines) + "\n"


def collect_hamravesh_paas(source: SourceConfig) -> PaasCollection:
    navigation = source.navigation
    result = fetch_with_browser(
        source.url,
        ready_marker=navigation.get("ready_marker", "هزینه منابع در پلتفرم ابری دارکوب"),
        click_selector=navigation.get("click_selector"),
    )
    rates = parse_hamravesh_paas_rates(result.html)
    quotes = rate_quotes(
        rates,
        provider_tier_raw="payg",
        region="ir-iran",
        product_family="paas_calculated",
        pricing_type="configurable_quote",
        plan_prefix="Hamravesh Darakub Iran",
        note_for=lambda key, selection: [IRAN_NOTE],
    )
    return PaasCollection(
        quotes=quotes,
        html=result.html,
        cleaned=_cleaned_markdown(rates, quotes),
    )
