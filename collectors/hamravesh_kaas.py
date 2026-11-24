"""Hamravesh managed-Kubernetes resource rates and current fee ladder.

The KaaS tab publishes two tables: monthly worker resource rates (vCore, RAM,
SSD) and a cluster-size management-fee ladder. The collected ladder is the
current self-service (v2) schedule; the dashboard's v1 comparison uses the
owner-provided legacy fixed costs from `benchmarks.yaml`, and the 240M top band
is assumed for the page's «ثبت درخواست» row. The page marks that band as quote
only, so no numeric tariff is stored for it.
"""
from __future__ import annotations

import re
from decimal import Decimal

from bs4 import BeautifulSoup

from collectors.arvan_fetch import fetch_with_browser
from collectors.common import FetchError
from collectors.kaas_pipeline import KaasCollection, KaasRate
from config.loader import SourceConfig
from normalization.persian import parse_price, to_latin_digits
from util.format import format_toman

RESOURCE_MARKERS = {
    "cpu": "vCore",
    "ram": "GB رم",
    "storage": "SSD",
}
RESOURCE_UNITS = {
    "cpu": "هر vCore",
    "ram": "هر گیگابایت",
    "storage": "هر گیگابایت",
}
REGION = "iran"


def parse_hamravesh_kaas(page_html: str) -> list[KaasRate]:
    """Worker rates plus numeric fee bands; quote-only bands are skipped."""
    soup = BeautifulSoup(page_html, "html.parser")
    rates: list[KaasRate] = []
    resources: dict[str, Decimal] = {}

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) != 3:
                continue
            label = cells[0]
            for key, marker in RESOURCE_MARKERS.items():
                if key in resources or marker not in label:
                    continue
                try:
                    resources[key] = parse_price(cells[2])
                except ValueError:
                    continue
            if len(resources) == len(RESOURCE_MARKERS):
                break
        if len(resources) == len(RESOURCE_MARKERS):
            break

    missing = set(RESOURCE_MARKERS) - set(resources)
    if missing:
        raise FetchError(f"Hamravesh KaaS rates missing: {sorted(missing)}")
    for key, amount in resources.items():
        rates.append(
            KaasRate(
                category=key,
                unit=RESOURCE_UNITS[key],
                tier_label="kaas",
                amount_toman=str(amount),
                evidence=f"Hamravesh KaaS ({REGION}): resource rate {format_toman(amount)}/month",
                region=REGION,
            )
        )

    previous_upper = 0
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) != 2 or "قیمت" in cells[0]:
                continue
            label, price_text = cells[0], cells[1]
            numbers = [int(n) for n in re.findall(r"\d+", to_latin_digits(label))]
            if not numbers:
                continue
            if "بیشتر" in label:
                lower, upper = numbers[0], None
            else:
                # Normalize the page's «تا N» bands to half-open [lower, N)
                # ranges; scenarios never sit exactly on 200/800/1500.
                lower, upper = previous_upper, numbers[0]
                previous_upper = upper
            try:
                amount = parse_price(price_text)
            except ValueError:
                continue  # quote-only band, not a numeric tariff
            tier_label = f"{lower}-{upper}" if upper is not None else f"{lower}-"
            rates.append(
                KaasRate(
                    category="management_fee",
                    unit="ماهانه",
                    tier_label=tier_label,
                    amount_toman=str(amount),
                    evidence=(
                        f"Hamravesh KaaS fee: {label} = "
                        f"{format_toman(amount)} Toman/month"
                    ),
                    region=REGION,
                )
            )
    if not any(rate.category == "management_fee" for rate in rates):
        raise FetchError("Hamravesh KaaS fee ladder has no numeric band")
    return rates


def _cleaned_markdown(rates: list[KaasRate]) -> str:
    lines = [
        "# Hamravesh managed Kubernetes tariffs (Iran datacenter)",
        "",
        "| category | tier | unit | monthly Toman |",
        "| --- | --- | --- | --- |",
    ]
    for rate in rates:
        lines.append(
            f"| {rate.category} | {rate.tier_label} | {rate.unit} | "
            f"{format_toman(rate.amount_toman, False)} |"
        )
    lines += [
        "",
        "The >1500-core fee band is quote-only on the source page and is not "
        "stored as a numeric tariff.",
    ]
    return "\n".join(lines) + "\n"


def collect_hamravesh_kaas(source: SourceConfig) -> KaasCollection:
    navigation = source.navigation
    result = fetch_with_browser(
        source.url,
        ready_marker=navigation.get(
            "ready_marker", "هزینه ثابت مدیریت هر کلاستر کوبرنتیز"
        ),
        click_selector=navigation.get("click_selector"),
    )
    rates = parse_hamravesh_kaas(result.html)
    return KaasCollection(
        rates=rates,
        html=result.html,
        cleaned=_cleaned_markdown(rates),
    )
