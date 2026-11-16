"""Deterministic extraction of Kubit's باکت (object storage) pricing.

Page structure (verified 2026-11-16, static HTML at kubit.cloud/fa/pricing/):
- h3 «پلن‌های باکت» → table: rows keyed by «عنوان», columns پایه / اختصاصی.
  The base plan is free with explicitly zero quotas (۰ گیگابایت / ۰) — zero
  is a source claim here; اختصاصی cells are «قابل مذاکره» (unknown, null) and
  its price is «توافقی» (quote-only).
- h3 «مصرف مازاد باکت» → table with columns عنوان / مصرف تا / واحد / قیمت:
  tiered storage (تا ۱۰ TB …), read/write requests per ۱۰٬۰۰۰, files, and
  four traffic rows (egress/ingress × inside/outside location).

Storage tier bounds are chained: «تا X» starts at 0, «مازاد تا X» continues
from the previous tier's upper bound, «بیش از X» runs unbounded. LRM marks
(‎) in the cells are stripped before parsing.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup


from collectors.arvan_os_rates import OSRateRow  # noqa: E402
from collectors.arvan_clean import sha256_text  # noqa: E402
from normalization.persian import parse_price, to_latin_digits  # noqa: E402

DEFAULT_TB_TO_GB = 1024
_NEGOTIABLE = "قابل مذاکره"


def _clean(text: str) -> str:
    """Strip LRM/RLM marks and collapse whitespace."""
    return re.sub(r"\s+", " ", (text or "").replace("\u200e", "").replace("\u200f", "")).strip()


def _bucket_table(soup: BeautifulSoup, heading_text: str):
    heading = soup.find(string=lambda s: s and _clean(s) == heading_text)
    if heading is None:
        return None
    started = heading.find_parent(["h2", "h3", "h4"])
    if started is None:
        return None
    table = started.find_next("table")
    return table


def _table_rows(table) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    return rows


@dataclass
class KubitOSPlan:
    plan_name: str
    price_raw: str
    storage_raw: str | None
    traffic_raw: str | None
    requests_raw: str | None
    unlimited_raw: str | None
    evidence: str
    # Kubit's overage rates live in the separate مصرف مازاد table (stored via
    # the rates parser); the plan matrix itself carries no per-GB overage text.
    overage_storage_raw: str | None = None
    overage_traffic_raw: str | None = None


def _parse_tb_gb(text: str, tb_to_gb: int) -> Decimal | None:
    """'۱۰ TB' -> 10240 (with the configured TB→GB factor)."""
    latin = to_latin_digits(_clean(text))
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*TB", latin)
    if match is None:
        return None
    return Decimal(match.group(1).replace(",", "")) * Decimal(tb_to_gb)


def parse_kubit_os_plans(page_html: str) -> list[KubitOSPlan]:
    soup = BeautifulSoup(page_html, "html.parser")
    table = _bucket_table(soup, "پلن‌های باکت")
    if table is None:
        raise ValueError("Kubit bucket plans table (پلن‌های باکت) not found on page")

    rows = _table_rows(table)
    header = rows[0]
    if not header or _clean(header[0]) != "عنوان":
        raise ValueError("unexpected Kubit bucket plans table shape")
    plan_names = header[1:]
    keyed: dict[str, list[str | None]] = {}
    for cells in rows[1:]:
        label = _clean(cells[0])
        values = [(v if v and v != _NEGOTIABLE else None) for v in cells[1:]]
        keyed[label] = values

    result: list[KubitOSPlan] = []
    for index, name in enumerate(plan_names):
        price_raw = (keyed.get("قیمت", [""] * len(plan_names))[index]) or ""
        storage_raw = keyed.get("فضای ذخیره‌سازی", [None] * len(plan_names))[index]
        traffic_raw = keyed.get("ترافیک خروجی", [None] * len(plan_names))[index]
        requests_raw = keyed.get("درخواست خواندن", [None] * len(plan_names))[index]
        evidence_parts = [f"پلن باکت {name}"]
        for label in ("فضای ذخیره‌سازی", "ترافیک خروجی", "درخواست خواندن", "قیمت"):
            value = keyed.get(label, [None] * len(plan_names))[index]
            if value:
                evidence_parts.append(f"{label}={value}")
        result.append(
            KubitOSPlan(
                plan_name=name,
                price_raw=price_raw,
                storage_raw=storage_raw,
                traffic_raw=traffic_raw,
                requests_raw=requests_raw,
                unlimited_raw=None,
                evidence="؛ ".join(evidence_parts),
            )
        )
    return result


def parse_kubit_os_rates(
    page_html: str, tb_to_gb: int = DEFAULT_TB_TO_GB
) -> list[OSRateRow]:
    soup = BeautifulSoup(page_html, "html.parser")
    table = _bucket_table(soup, "مصرف مازاد باکت")
    if table is None:
        raise ValueError("Kubit bucket overage table (مصرف مازاد باکت) not found on page")

    rates: list[OSRateRow] = []
    prev_max: Decimal | None = None
    for cells in _table_rows(table)[1:]:
        if len(cells) != 4:
            continue
        label, range_text, unit, price_text = cells
        try:
            amount = str(parse_price(price_text))
        except ValueError:
            continue
        is_free = "رایگان" in price_text
        if _clean(label).startswith("فضای ذخیره‌سازی"):
            lo: Decimal | None
            hi: Decimal | None
            if range_text.startswith("تا"):
                lo, hi = Decimal("0"), _parse_tb_gb(range_text, tb_to_gb)
            elif range_text.startswith("مازاد تا"):
                lo, hi = prev_max, _parse_tb_gb(range_text, tb_to_gb)
            elif range_text.startswith("بیش از"):
                lo, hi = prev_max, None
            else:
                lo, hi = None, None
            if hi is not None:
                prev_max = hi
            rates.append(OSRateRow(
                category="storage", unit=unit, tier_label="",
                range_label=range_text,
                range_min_gb=str(lo) if lo is not None else None,
                range_max_gb=str(hi) if hi is not None else None,
                amount_toman=None if is_free else amount, is_free=is_free,
                evidence=f"باکت/{label}/{range_text}: {price_text}",
            ))
        elif label == "درخواست خواندن":
            rates.append(OSRateRow(
                category="requests_read", unit=unit, tier_label="", range_label="",
                range_min_gb=None, range_max_gb=None,
                amount_toman=None if is_free else amount, is_free=is_free,
                evidence=f"باکت/{label}: {price_text}",
            ))
        elif label == "درخواست نوشتن":
            rates.append(OSRateRow(
                category="requests_write", unit=unit, tier_label="", range_label="",
                range_min_gb=None, range_max_gb=None,
                amount_toman=None if is_free else amount, is_free=is_free,
                evidence=f"باکت/{label}: {price_text}",
            ))
        elif label.startswith("تعداد فایل"):
            rates.append(OSRateRow(
                category="feature", unit=unit, tier_label=label, range_label="",
                range_min_gb=None, range_max_gb=None,
                amount_toman=None if is_free else amount, is_free=is_free,
                evidence=f"باکت/{label}: {price_text}",
            ))
        elif label.startswith("ترافیک"):
            rates.append(OSRateRow(
                category="traffic", unit=unit, tier_label=label, range_label="",
                range_min_gb=None, range_max_gb=None,
                amount_toman=None if is_free else amount, is_free=is_free,
                evidence=f"باکت/{label}: {price_text}",
            ))
    return rates


def clean_kubit_os(page_html: str, source_url: str) -> str:
    """Cleaned باکت section (plans + overage tables) for evidence and hashing."""
    soup = BeautifulSoup(page_html, "html.parser")
    plans_table = _bucket_table(soup, "پلن‌های باکت")
    rates_table = _bucket_table(soup, "مصرف مازاد باکت")
    if plans_table is None or rates_table is None:
        raise ValueError("Kubit bucket pricing tables not found on page")

    def table_markdown(table) -> str:
        rows = _table_rows(table)
        if not rows:
            return ""
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * len(rows[0])]
        for cells in rows[1:]:
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)

    lines = [
        f"# Kubit bucket (object storage) pricing\nSource: {source_url}\n",
        "## پلن‌های باکت",
        table_markdown(plans_table),
        "",
        "## مصرف مازاد باکت",
        table_markdown(rates_table),
        "",
        "به هزینه‌های قید شده، ۱۰٪ مالیات بر ارزش افزوده اضافه می‌شود؛ ماه = دوره ۳۰ روزه.",
    ]
    return "\n".join(lines) + "\n"
