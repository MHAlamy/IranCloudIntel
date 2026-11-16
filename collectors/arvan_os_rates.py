"""Deterministic extraction of Arvan Object Storage PAYG data.

Page structure (verified 2026-11-15):
- The 'مصرف مازاد' (overage) section is a flex-div grid: a header row per
  category ('ذخیره‌سازی' / 'درخواست‌ خواندن' / 'درخواست‌ نوشتن' / 'ترافیک' /
  'قابلیت‌ها') with the billing unit, then (tier, range, amount) rows where
  empty first cells continue the previous tier/group.
- The plan comparison matrix is a real <table> (features × plan columns);
  plan names live in the cards above it, so columns are positional.
- The marketing FAQ also mentions overage figures. It is not part of the
  published tariff table and is intentionally not collected (owner decision
  2026-11-16: the rate table is authoritative).

Range bounds are parsed to GB only for GB-denominated categories (storage,
traffic); request-tier ranges keep their verbatim labels (scenario math
excludes requests because Hamravesh publishes no request allowance).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup


from normalization.persian import parse_price, to_latin_digits  # noqa: E402

DEFAULT_TB_TO_GB = 1024

# Verbatim group labels -> stable category keys (ZWNJ-insensitive)
_CATEGORY_KEYS = {
    "ذخیرهسازی": "storage",
    "درخواست خواندن": "requests_read",
    "درخواست نوشتن": "requests_write",
    "ترافیک": "traffic",
    "قابلیتها": "feature",
}


def _category_key(label: str) -> str:
    compact = (label or "").replace("\u200c", "").strip()
    return _CATEGORY_KEYS.get(compact, compact)


@dataclass
class OSRateRow:
    category: str      # storage | traffic_download | requests_read | requests_write | feature
    unit: str
    tier_label: str
    range_label: str
    range_min_gb: str | None
    range_max_gb: str | None
    amount_toman: str | None  # None when is_free
    is_free: bool
    evidence: str


def _unit_factor(text: str, tb_to_gb: int) -> Decimal | None:
    if "ترابایت" in text:
        return Decimal(tb_to_gb)
    if "پتابایت" in text:
        return Decimal(tb_to_gb) * Decimal(1024)
    if "گیگابایت" in text:
        return Decimal(1)
    return None


def _parse_side(side: str, unit_hint: str, tb_to_gb: int) -> Decimal | None:
    latin = to_latin_digits(side)
    match = re.search(r"\d+(?:[.,]\d+)?", latin)
    if match is None:
        return None
    number = Decimal(match.group(0).replace(",", ""))
    factor = _unit_factor(side, tb_to_gb) or _unit_factor(unit_hint, tb_to_gb)
    if factor is None:
        return None
    return number * factor


def parse_gb_bounds(range_label: str, tb_to_gb: int = DEFAULT_TB_TO_GB):
    """'۵ گیگابایت تا ۵ ترابایت' -> (5, 5120); 'بیش از ۵۰۰ ترابایت' -> (512000, None).

    Note: 'پتابایت' contains the substring 'تا', so the تا split must be
    word-boundary aware and 'بیش از'/'تا' prefixes are handled first.
    """
    text = (range_label or "").strip()
    if not text:
        return None, None
    if text.startswith("بیش از"):
        return _parse_side(text, text, tb_to_gb), None
    if text.startswith("تا"):
        return Decimal("0"), _parse_side(text, text, tb_to_gb)
    parts = re.split(r"\s+تا\s+", text)
    if len(parts) == 2:
        low = _parse_side(parts[0], parts[1], tb_to_gb)
        high = _parse_side(parts[1], parts[1], tb_to_gb)
        return low, high
    return None, None


def _payg_blocks(soup: BeautifulSoup) -> list:
    """All flex-row blocks of the 'مصرف مازاد' section.

    The section is one wrapper div containing the heading plus one
    div.rounded-lg per category block (storage / read requests / write
    requests / traffic / features).
    """
    heading = soup.find(string=lambda s: s and s.strip() == "مصرف مازاد")
    if heading is None:
        return []
    block = heading.find_parent("div")
    if block is None:
        return []
    rounded_blocks = block.find_all("div", class_="rounded-lg")
    return rounded_blocks or [block]


def parse_os_rates(page_html: str, tb_to_gb: int = DEFAULT_TB_TO_GB) -> list[OSRateRow]:
    soup = BeautifulSoup(page_html, "html.parser")
    blocks = _payg_blocks(soup)
    if not blocks:
        raise ValueError("Arvan object-storage PAYG section (مصرف مازاد) not found on page")

    rates: list[OSRateRow] = []
    category = unit = tier = ""
    for container in blocks:
        for row in container.find_all("div", class_="flex"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("div", recursive=False)]
            if len(cells) == 3:
                group, range_text, amount_text = cells
                if range_text == "پلکان استفاده":
                    category, unit, tier = _category_key(group), amount_text, ""
                    continue
                if not category or not range_text or not amount_text:
                    continue
                if group:
                    tier = group
                min_gb, max_gb = (
                    parse_gb_bounds(range_text, tb_to_gb) if "گیگابایت" in unit else (None, None)
                )
                rates.append(_make_row(category, unit, tier, range_text, amount_text, min_gb, max_gb))
            elif len(cells) == 2:
                label, value = cells
                if value.startswith("هر "):
                    category, unit, tier = _category_key(label), value, ""
                    continue
                if not category or not label or not value:
                    continue
                rates.append(_make_row(category, unit, label, "", value, None, None))
    return rates


def _make_row(
    category: str, unit: str, tier: str, range_label: str, amount_text: str,
    min_gb: Decimal | None, max_gb: Decimal | None,
) -> OSRateRow:
    is_free = "رایگان" in amount_text
    amount: str | None = None
    if not is_free:
        try:
            amount = str(parse_price(amount_text))
        except ValueError:
            amount = None
    return OSRateRow(
        category=category,
        unit=unit,
        tier_label=tier,
        range_label=range_label,
        range_min_gb=str(min_gb) if min_gb is not None else None,
        range_max_gb=str(max_gb) if max_gb is not None else None,
        amount_toman=amount,
        is_free=is_free,
        evidence=f"{category}/{tier or '-'}/{range_label or '-'}: {amount_text}",
    )


def parse_os_plan_matrix(page_html: str) -> dict[str, list[str]]:
    """The plan comparison table, column-ordered (plan names live in the cards).

    Returns e.g. {'storage': ['۵ گیگابایت', '۵۰۰ گیگابایت', '۵ ترابایت', 'نامحدود'],
                  'traffic': [...], 'requests': [...]}.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    wanted = {
        "فضای ذخیره‌سازی": "storage",
        "ترافیک": "traffic",
        "درخواست خواندن/نوشتن": "requests",
    }
    result: dict[str, list[str]] = {}
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) < 2:
                continue
            key = wanted.get(cells[0])
            if key and key not in result:
                result[key] = cells[1:]
    return result


def crosscheck_arvan_os_plans(page_html: str, normalized_pairs: list) -> list[dict]:
    """Review-only check: LLM plan rows vs the page's own comparison matrix.

    Matrix columns and plan cards are both in display order, so rows are
    compared positionally. Any mismatch or structural surprise becomes a
    review entry; nothing is auto-rejected.
    """
    from normalization.os_validate import parse_capacity_gb

    matrix = parse_os_plan_matrix(page_html)
    entries: list[dict] = []
    if not matrix:
        return [{"check": "matrix", "error": "plan comparison matrix not found on page"}]

    storage_cols = matrix.get("storage") or []
    traffic_cols = matrix.get("traffic") or []
    request_cols = matrix.get("requests") or []
    if not (len(storage_cols) == len(traffic_cols) == len(request_cols)):
        entries.append({"check": "matrix", "error": "matrix rows have different column counts"})
        return entries
    if len(normalized_pairs) != len(storage_cols):
        entries.append({
            "check": "plan_count",
            "llm_plans": len(normalized_pairs),
            "matrix_columns": len(storage_cols),
        })
        return entries

    for index, (raw, normalized) in enumerate(normalized_pairs):
        for dim, matrix_raw, normalized_value, unlimited in (
            ("storage", storage_cols[index], normalized.storage_included_gb, normalized.storage_unlimited),
            ("traffic", traffic_cols[index], normalized.traffic_included_gb, normalized.traffic_unlimited),
        ):
            matrix_unlimited = "نامحدود" in matrix_raw
            try:
                matrix_gb = parse_capacity_gb(matrix_raw)
            except ValueError:
                entries.append({"check": dim, "plan": raw.plan_name, "matrix_raw": matrix_raw,
                                "error": "matrix capacity unparsable"})
                continue
            if matrix_unlimited != unlimited or (
                not matrix_unlimited and matrix_gb is not None
                and normalized_value is not None and matrix_gb != normalized_value
            ):
                entries.append({
                    "check": dim, "plan": raw.plan_name,
                    "matrix": matrix_raw, "llm": str(normalized_value),
                    "llm_unlimited": unlimited, "matrix_unlimited": matrix_unlimited,
                })
        # request allowance (matrix value is a plain count)
        matrix_requests = request_cols[index]
        if "نامحدود" in matrix_requests:
            matrix_requests_unlimited = True
            matrix_requests_count = None
        else:
            matrix_requests_unlimited = False
            try:
                matrix_requests_count = int(parse_price(matrix_requests))
            except ValueError:
                matrix_requests_count = None
        if matrix_requests_unlimited != normalized.requests_unlimited or (
            not matrix_requests_unlimited
            and matrix_requests_count is not None
            and normalized.requests_included is not None
            and matrix_requests_count != normalized.requests_included
        ):
            entries.append({
                "check": "requests", "plan": raw.plan_name,
                "matrix": matrix_requests, "llm": normalized.requests_included,
                "llm_unlimited": normalized.requests_unlimited,
            })
    return entries
