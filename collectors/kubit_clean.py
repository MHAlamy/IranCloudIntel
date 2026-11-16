"""Cleaned-content builder for Kubit's rate-table page (evidence + hash)."""

from __future__ import annotations

import sys
from pathlib import Path


from collectors.arvan_clean import TabContent, sha256_text  # noqa: E402
from collectors.kubit_rates import parse_kubit_rates  # noqa: E402


def clean_kubit(page_html: str, source_url: str, tabs) -> dict[str, TabContent]:
    """Produce the cleaned rate-table markdown (the hash basis for skip-unchanged)."""
    rates = parse_kubit_rates(page_html)
    lines = [
        "# Kubit IaaS infrastructure rates",
        f"Source: {source_url}",
        "",
        "| عنوان | نسل | واحد | قیمت |",
        "| --- | --- | --- | --- |",
    ]
    for r in rates:
        label = r.tier_label.replace("gen-", "نسل ") or "—"
        lines.append(f"| {r.category} | {label} | {r.unit} | {r.amount_toman} تومان |")
    markdown = "\n".join(lines) + "\n"
    return {"rates": TabContent(tab="rates", markdown=markdown, rows=[], content_hash=sha256_text(markdown))}
