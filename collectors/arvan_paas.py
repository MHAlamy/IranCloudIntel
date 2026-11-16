"""Arvan PaaS PAYG monthly rates and calculated quotes."""
from __future__ import annotations

import re
from decimal import Decimal

from bs4 import BeautifulSoup

from collectors.arvan_fetch import fetch_with_browser
from collectors.common import FetchError
from collectors.paas_pipeline import PaasCollection, rate_quotes
from config.loader import SourceConfig
from normalization.persian import parse_price
from util.format import format_toman

BASE_NOTE = "محاسبه‌شده از نرخ‌های PAYG رسمی؛ بدون ترافیک، IPv4، بکاپ و اسنپ‌شات"
SMALL_NOTE = (
    "کوچک‌ترین ترکیب در ماشین‌حساب عمومی آروان قابل انتخاب نیست؛ "
    "قیمت از نرخ‌های PAYG محاسبه شده است"
)
LARGE_DISK_NOTE = (
    "حجم SSD فراتر از سقف اسلایدر ماشین‌حساب آروان (۲۰۰ GB) است؛ "
    "قیمت از نرخ‌های PAYG محاسبه شده است"
)

_PRICE_RE = re.compile(r"([\d۰-۹٠-٩][\d۰-۹٠-٩٬,\.]*)\s*تومان")


def _find_amount(
    soup: BeautifulSoup, required: tuple[str, ...], forbidden: tuple[str, ...] = (),
) -> Decimal | None:
    """Smallest element whose text carries all required labels and a Toman amount."""
    candidates: list[tuple[int, Decimal]] = []
    for el in soup.find_all(["div", "span", "p", "td", "li"]):
        text = el.get_text(" ", strip=True)
        if not text or len(text) > 220:
            continue
        if not all(marker in text for marker in required):
            continue
        if any(marker in text for marker in forbidden):
            continue
        match = _PRICE_RE.search(text)
        if not match:
            continue
        try:
            amount = parse_price(match.group(1))
        except ValueError:
            continue
        candidates.append((len(text), amount))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def parse_arvan_paas_rates(page_html: str) -> dict[str, Decimal]:
    soup = BeautifulSoup(page_html, "html.parser")
    rates = {
        "cpu": _find_amount(soup, ("هر vCore",)),
        "ram": _find_amount(soup, ("هر گیگابایت", "RAM")),
        "storage": _find_amount(soup, ("دیسک SSD",), ("موقت", "Ephemeral")),
    }
    missing = [key for key, value in rates.items() if value is None]
    if missing:
        raise FetchError(f"Arvan PaaS rates missing: {missing}")
    return {key: value for key, value in rates.items() if value is not None}


def _note_for(key: str, selection) -> list[str]:
    notes = [BASE_NOTE]
    if key == "s1":
        notes.append(SMALL_NOTE)
    if key in ("s3", "s4"):
        notes.append(LARGE_DISK_NOTE)
    return notes


def _cleaned_markdown(rates: dict[str, Decimal], quotes) -> str:
    lines = [
        "# ArvanCloud PaaS (container) monthly PAYG resource rates",
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


def collect_arvan_paas(source: SourceConfig) -> PaasCollection:
    result = fetch_with_browser(
        source.url,
        ready_marker=source.navigation.get("ready_marker", "هر vCore"),
    )
    rates = parse_arvan_paas_rates(result.html)
    quotes = rate_quotes(
        rates,
        provider_tier_raw="payg",
        region="ir-thr-ba1",
        product_family="paas_calculated",
        pricing_type="configurable_quote",
        plan_prefix="Arvan PaaS PAYG",
        note_for=_note_for,
    )
    return PaasCollection(
        quotes=quotes,
        html=result.html,
        cleaned=_cleaned_markdown(rates, quotes),
    )
