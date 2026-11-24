"""Kubit managed-Kubernetes licence ladder and worker resource tariffs.

Kubit publishes a tiered Kubernetes licence fee keyed on
`P = 2 × vCPU + RAM(GB)`, plus the normal IaaS component rates for the worker
nodes. The top band (P ≥ 8000) is "contact sales", so it is not stored.
The dashboard compares workers at the published generation-4 (Standard) rates.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from collectors.common import FetchError
from collectors.fetching import fetch_source
from collectors.kaas_pipeline import KaasCollection, KaasRate
from collectors.kubit_rates import parse_kubit_rates
from config.loader import SourceConfig
from normalization.persian import parse_price, to_latin_digits
from util.format import format_toman

WORKER_CATEGORIES = ("cpu", "ram", "storage")


def parse_kubit_kaas_fees(page_html: str) -> list[KaasRate]:
    soup = BeautifulSoup(page_html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        header = candidate.find("tr")
        if header is None:
            continue
        headers = [c.get_text(" ", strip=True) for c in header.find_all(["th", "td"])]
        if any("P" in header_text for header_text in headers) and any(
            "قیمت" in header_text for header_text in headers
        ):
            table = candidate
            break
    if table is None:
        raise FetchError("Kubit KaaS fee table not found")

    rates: list[KaasRate] = []
    for tr in table.find_all("tr")[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        label, price_text = cells[0], cells[1]
        numbers = [int(n) for n in re.findall(r"\d+", to_latin_digits(label))]
        if not numbers:
            continue
        lower = numbers[0]
        upper = numbers[1] if len(numbers) > 1 else None
        try:
            amount = parse_price(price_text)
        except ValueError:
            continue  # "contact sales" band
        tier_label = f"{lower}-{upper}" if upper is not None else f"{lower}-"
        rates.append(
            KaasRate(
                category="management_fee",
                unit="ماهانه",
                tier_label=tier_label,
                amount_toman=str(amount),
                evidence=(
                    f"Kubit KaaS licence: {label} = "
                    f"{format_toman(amount)} Toman/month"
                ),
            )
        )
    if not rates:
        raise FetchError("Kubit KaaS fee ladder has no numeric band")
    return rates


def parse_kubit_kaas(page_html: str) -> list[KaasRate]:
    workers = [
        KaasRate(
            category=rate.category,
            unit=rate.unit,
            tier_label=rate.tier_label,
            amount_toman=rate.amount_toman,
            evidence=rate.evidence,
        )
        for rate in parse_kubit_rates(page_html)
        if rate.category in WORKER_CATEGORIES
    ]
    if not workers:
        raise FetchError("Kubit IaaS worker rates not found")
    return workers + parse_kubit_kaas_fees(page_html)


def _cleaned_markdown(rates: list[KaasRate]) -> str:
    lines = [
        "# Kubit managed Kubernetes tariffs",
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
        "Worker resources use the published generation-4 (Standard) rates. "
        "The P >= 8000 licence band is contact-sales only and is not stored.",
    ]
    return "\n".join(lines) + "\n"


def collect_kubit_kaas(source: SourceConfig) -> KaasCollection:
    result = fetch_source(source)
    rates = parse_kubit_kaas(result.html)
    return KaasCollection(
        rates=rates,
        html=result.html,
        cleaned=_cleaned_markdown(rates),
    )
