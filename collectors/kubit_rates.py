"""Deterministic extraction of Kubit's IaaS infrastructure rate table.

Kubit prices VMs purely by component rates (no bundles): CPU and RAM by
generation (نسل ۳/۴), disk per GB, internet/floating IPv4 per month, traffic
per GB. Source page is static HTML (plain HTTP works).

Owner decisions (2026-11-15): gen-3 maps to Economy, gen-4 to Standard, no
premium; VAT and traffic are out of comparison scope.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from normalization.persian import parse_price, to_latin_digits  # noqa: E402

CATEGORY_BY_TITLE = {
    "پردازنده": "cpu",
    "حافظه": "ram",
    "دیسک": "storage",
    "آی‌پی اینترنتی ipv4": "ipv4",
    "آی‌پی شناور ipv4": "ipv4",
    "ترافیک دانلود": "traffic",
    "ترافیک آپلود": "traffic",
}
TIER_BY_TITLE = {
    "آی‌پی اینترنتی ipv4": "internet",
    "آی‌پی شناور ipv4": "floating",
    "ترافیک دانلود": "download",
    "ترافیک آپلود": "upload",
}
UNIT_BY_CATEGORY = {
    "cpu": "هر vCPU",
    "ram": "هر گیگابایت",
    "storage": "هر گیگابایت",
    "ipv4": "هر آدرس",
    "traffic": "هر گیگابایت",
}


@dataclass
class KubitRateRow:
    category: str
    region: str
    unit: str
    tier_label: str
    amount_toman: str
    evidence: str


def _category(title: str) -> str | None:
    return CATEGORY_BY_TITLE.get((title or "").strip().lower())


def parse_kubit_rates(page_html: str) -> list[KubitRateRow]:
    """Parse the IaaS rate table (header: عنوان | نسل | واحد | قیمت)."""
    soup = BeautifulSoup(page_html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        header = candidate.find("tr")
        if header is None:
            continue
        headers = [c.get_text(" ", strip=True) for c in header.find_all(["th", "td"])]
        if headers[:2] == ["عنوان", "نسل"] and "قیمت" in headers:
            table = candidate
            break
    if table is None:
        return []

    rates: list[KubitRateRow] = []
    for tr in table.find_all("tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) < 4:
            continue
        title, generation, _unit, price_text = cells[0], cells[1], cells[2], cells[3]
        category = _category(title)
        if category is None:
            continue
        if "رایگان" in price_text:
            amount = "0"
        else:
            try:
                amount = str(parse_price(price_text))
            except ValueError:
                continue
        tier_label = TIER_BY_TITLE.get(title.strip().lower(), "")
        if category in ("cpu", "ram") and generation:
            tier_label = f"gen-{to_latin_digits(generation).strip()}"
        rates.append(
            KubitRateRow(
                category=category,
                region="iran",
                unit=UNIT_BY_CATEGORY[category],
                tier_label=tier_label,
                amount_toman=amount,
                evidence=f"kubit/iran/{title} ({generation or '-'}): {price_text}",
            )
        )
    return rates
