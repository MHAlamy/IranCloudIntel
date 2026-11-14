"""Deterministic cleaning of Arvan cloud-server pricing pages.

Input: the rendered page HTML (captured with a real browser).
Output: per-tab cleaned markdown (the only text sent to the LLM) plus parsed
row metadata used for evidence and hashing.

Design notes from inspection (2026-11-14):
- The page server-renders three Alpine panels (x-show="active === 'basic' |
  'standard' | 'premium'"); tab visibility is toggled client-side.
- Each panel contains a real <table>; rows carry an onclick purchase URL that
  exposes the plan id and region (az=...), used as evidence metadata.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

PANEL_ATTR_RE = re.compile(r"active === '(basic|standard|premium)'")
ONCLICK_URL_RE = re.compile(r"window\.open\('([^']+)'")
REGION_RE = re.compile(r"[?&]az=([\w-]+)")

TABLE_HEADERS = ("نام", "پردازنده", "حافظه", "دیسک", "قیمت ماهانه")


@dataclass
class PlanRow:
    plan_name: str
    cpu_raw: str
    ram_raw: str
    disk_raw: str
    price_raw: str
    currency_raw: str
    billing_raw: str
    region: str | None
    plan_url: str | None
    evidence: str = field(default="")


@dataclass
class TabContent:
    tab: str
    markdown: str
    rows: list[PlanRow]
    content_hash: str


def extract_panel_html(page_html: str, tab: str) -> str:
    """Return the panel div HTML for one tab, or raise ValueError."""
    if tab not in ("basic", "standard", "premium"):
        raise ValueError(f"unknown tab {tab!r}")
    soup = BeautifulSoup(page_html, "html.parser")
    for el in soup.find_all(attrs={"x-show": PANEL_ATTR_RE}):
        if f"active === '{tab}'" in (el.get("x-show") or ""):
            return str(el)
    raise ValueError(f"no panel found for tab {tab!r}")


def parse_plan_rows(panel_html: str) -> list[PlanRow]:
    """Parse the pricing table inside one panel into structured rows."""
    soup = BeautifulSoup(panel_html, "html.parser")
    rows: list[PlanRow] = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue  # header or decorative rows
        onclick = (tr.get("onclick") or "")
        url_match = ONCLICK_URL_RE.search(onclick)
        plan_url = url_match.group(1).replace("&", "&") if url_match else None
        region = None
        if plan_url:
            region_match = REGION_RE.search(plan_url)
            region = region_match.group(1) if region_match else None
        name = cells[0].get_text(" ", strip=True)
        price_lines = [ln.strip() for ln in cells[4].get_text("\n").split("\n") if ln.strip()]
        price_raw = price_lines[0] if price_lines else ""
        currency_raw = price_lines[1] if len(price_lines) > 1 else ""
        evidence = " | ".join(c.get_text(" ", strip=True) for c in cells[:5])
        rows.append(
            PlanRow(
                plan_name=name,
                cpu_raw=cells[1].get_text(" ", strip=True),
                ram_raw=cells[2].get_text(" ", strip=True),
                disk_raw=cells[3].get_text(" ", strip=True),
                price_raw=price_raw,
                currency_raw=currency_raw,
                billing_raw="ماهانه",  # column header is قیمت ماهانه
                region=region,
                plan_url=plan_url,
                evidence=evidence,
            )
        )
    return rows


def build_cleaned_markdown(tab: str, rows: list[PlanRow], source_url: str) -> str:
    """Deterministic cleaned content for one tab (what the LLM receives)."""
    lines = [
        f"# ArvanCloud cloud-server pricing — tab: {tab}",
        f"Source: {source_url}",
        "",
        "| " + " | ".join(TABLE_HEADERS) + " | region |",
        "|" + " --- |" * 7,
    ]
    for r in rows:
        lines.append(
            f"| {r.plan_name} | {r.cpu_raw} | {r.ram_raw} | {r.disk_raw} "
            f"| {r.price_raw} {r.currency_raw} | {r.region or '-'} |"
        )
    return "\n".join(lines) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_page(page_html: str, source_url: str, tabs: tuple[str, ...] = ("basic", "standard", "premium")) -> dict[str, TabContent]:
    """Clean all requested tabs from a rendered page."""
    result: dict[str, TabContent] = {}
    for tab in tabs:
        panel_html = extract_panel_html(page_html, tab)
        rows = parse_plan_rows(panel_html)
        markdown = build_cleaned_markdown(tab, rows, source_url)
        result[tab] = TabContent(
            tab=tab, markdown=markdown, rows=rows, content_hash=sha256_text(markdown)
        )
    return result
