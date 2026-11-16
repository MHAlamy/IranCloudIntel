"""Cleaning of Arvan Object Storage pricing pages for LLM extraction.

The rendered page contains, in order: plan cards (پایه/رشد/حرفه‌ای/سازمانی
with prices), a plan-comparison matrix, the PAYG 'مصرف مازاد' rate tables and
an FAQ. The LLM receives only the plans region — from the 'قیمت فضای ابری'
heading to just before 'مصرف مازاد' — so extraction stays focused and the
deterministic rate parser (arvan_os_rates.py) owns the PAYG tables.

The PAYG/FAQ region is deliberately excluded: the deterministic rate parser
owns the tariff table, and the marketing FAQ is not collected at all (owner
decision 2026-11-16: the rate table is authoritative).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from bs4 import BeautifulSoup


START_ANCHOR = "قیمت فضای ابری"
END_ANCHOR = "مصرف مازاد"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_os_cleaned_markdown(page_html: str, source_url: str) -> str:
    """Linearized, noise-free text of the plans region of the storage page."""
    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    try:
        start = next(i for i, line in enumerate(lines) if line == START_ANCHOR)
    except StopIteration as exc:
        raise ValueError(f"anchor {START_ANCHOR!r} not found on the Arvan storage page") from exc
    end_candidates = [i for i, line in enumerate(lines) if line == END_ANCHOR and i > start]
    if not end_candidates:
        raise ValueError(f"anchor {END_ANCHOR!r} not found after the plans region")
    end = end_candidates[0]

    body = "\n".join(lines[start:end])
    return (
        f"# ArvanCloud object-storage pricing\nSource: {source_url}\n\n{body}\n"
    )
