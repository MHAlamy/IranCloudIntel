"""Deterministic extraction of Arvan's PAYG component rate tables.

Page structure (verified 2026-11-15): each category is a div.scroll-items
section (id pricing-package-N) containing two Alpine panes,
div[x-show="region === 'iran'"] and div[x-show="region === 'europe'"].
Inside a pane: a category label line, a unit line ('هر vCore' etc.), and rows
of (label, price) pairs. Europe pane tables explain the ×7/6 price pairs.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag


from normalization.persian import parse_price  # noqa: E402

CATEGORY_ALIASES = {
    "پردازنده": "cpu",
    "پردازنده گرافیکی": "gpu",
    "حافظه (ram)": "ram",
    "فضای ذخیره‌سازی": "storage",
    "نشانی آی‌پی": "ipv4",
    "ترافیک": "traffic",
    "سرور اختصاصی": "dedicated",
}


@dataclass
class RateRow:
    category: str
    region: str
    unit: str
    tier_label: str
    amount_toman: str  # Decimal text
    evidence: str


def _category_key(text: str) -> str | None:
    return CATEGORY_ALIASES.get((text or "").strip().lower())


def _extract_pane_rows(pane: Tag) -> list[tuple[str, str]]:
    """Return (label, price_text) pairs from a pane.

    Row divs contain 'items-center' in their class list (BS4 calls class_
    callables per token, and the last row of a table lacks 'border-b').
    """
    rows: list[tuple[str, str]] = []
    for row in pane.find_all("div", class_=re.compile(r"items-center")):
        parts = row.find_all("div", recursive=False)
        if len(parts) < 2:
            continue
        # label is the wider text part; price contains a number + تومان
        texts = [p.get_text(" ", strip=True) for p in parts]
        price_text = next((t for t in texts if "تومان" in t), None)
        if price_text is None:
            continue
        label = next((t for t in texts if t != price_text and t), "")
        if label:
            rows.append((label, price_text))
    return rows


def _pane_unit(pane: Tag) -> str:
    """The pane's unit header: first 'هر …' line in its text."""
    for line in pane.get_text("\n", strip=True).split("\n"):
        line = line.strip()
        if line.startswith("هر "):
            return line
    return ""


def _pane_category(pane: Tag) -> str | None:
    """The pane's category: first recognized category label in its text."""
    for line in pane.get_text("\n", strip=True).split("\n"):
        key = _category_key(line)
        if key:
            return key
    return None


def parse_rates(page_html: str) -> list[RateRow]:
    soup = BeautifulSoup(page_html, "html.parser")
    rates: list[RateRow] = []
    for section in soup.find_all("div", class_="scroll-items"):
        for pane in section.find_all(attrs={"x-show": re.compile("region === '(iran|europe)'")}):
            region = "iran" if "'iran'" in (pane.get("x-show") or "") else "europe"
            category = _pane_category(pane)
            unit = _pane_unit(pane)
            if category is None:
                continue
            for label, price_text in _extract_pane_rows(pane):
                try:
                    amount = parse_price(price_text)
                except ValueError:
                    continue
                evidence = f"{category}/{region}/{unit}/{label}: {price_text}"
                rates.append(
                    RateRow(
                        category=category,
                        region=region,
                        unit=unit,
                        tier_label=label,
                        amount_toman=str(amount),
                        evidence=evidence,
                    )
                )
    return rates
