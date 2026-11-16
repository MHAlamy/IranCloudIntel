"""Deterministic parsing of Liara's IaaS (سرور مجازی ابری) bundle plans.

Liara publishes fixed bundles on the cloud-server product page (div-based,
planet-named plans). The same planet names repeat for PaaS/DBaaS sections with
different specs/prices, so parsing is scoped to the IaaS section: from the
section heading before the disclosure text («موقعیت تمامی پلن‌ها ایران…»).

The page also documents the IPv4 surcharge («ماهانه ۲۰۰ هزار تومان … هزینه‌ی
IPv4 به قیمت‌های بالا اضافه می‌شود»), parsed and added to the comparable
monthly price.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup


from normalization.persian import parse_price  # noqa: E402


@dataclass
class LiaraPlan:
    name: str
    monthly_text: str
    monthly_toman: str
    hourly_toman: str
    ram_gb: str
    vcpu: str
    disk_gb: str


SECTION_START = "پلن‌های سرور"
SECTION_END = "موقعیت تمامی پلن‌ها"

DETAIL_RE = re.compile(
    r"^(?P<name>[^\n]+)\n"
    r"قیمت ماهانه\n(?P<monthly>[\d۰-۹,٬]+)\nتومان\n"
    r"قیمت ساعتی\n(?P<hourly>[\d۰-۹,٬]+)\nتومان\n"
    r"RAM\n\(GB\)\n(?P<ram>[\d.۰-۹]+)\n"
    r"vCPU\n\(CORE\)\n(?P<vcpu>[\d.۰-۹]+)\n"
    r"Disk\n\(GB SSD\)\n(?P<disk>[\d.۰-۹]+)",
    re.MULTILINE,
)
IPV4_RE = re.compile(r"ماهانه\s+(?P<amount>[\d۰-۹,٬]+)\s*هزار\s*تومان[^\n]*IPv4")


def _section_text(page_html: str) -> str:
    """Slice the IaaS section out of the page text.

    Product page: section heading is 'قیمت‌ پلن‌های سرور‌ مجازی ابری'.
    Pricing page: the IaaS heading lacks that phrase — fall back to the last
    'سرور مجازی ابری' occurrence before the Iran-location disclosure.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    text = soup.get_text("\n", strip=True)
    end = text.find(SECTION_END)
    if end < 0:
        return ""
    start = text.rfind(SECTION_START, 0, end)
    if start < 0:
        start = text.rfind("سرور مجازی ابری", 0, end)
    if start < 0:
        return ""
    return text[start:end]


def parse_ipv4_monthly(page_html: str) -> str | None:
    """Parse the documented IPv4 monthly surcharge ('۲۰۰ هزار تومان' -> 200000)."""
    soup = BeautifulSoup(page_html, "html.parser")
    text = soup.get_text("\n", strip=True)
    match = IPV4_RE.search(text)
    if match is None:
        return None
    amount = parse_price(match.group("amount"))
    return str(amount * 1000)  # 'هزار' = thousands


def parse_liara_plans(page_html: str) -> list[LiaraPlan]:
    section = _section_text(page_html)
    if not section:
        return []
    plans: list[LiaraPlan] = []
    for match in DETAIL_RE.finditer(section):
        plans.append(
            LiaraPlan(
                name=match.group("name").strip(),
                monthly_text=f"{match.group('monthly')} تومان",
                monthly_toman=str(parse_price(match.group("monthly"))),
                hourly_toman=str(parse_price(match.group("hourly"))),
                ram_gb=str(parse_price(match.group("ram"))),
                vcpu=str(parse_price(match.group("vcpu"))),
                disk_gb=str(parse_price(match.group("disk"))),
            )
        )
    return plans
