"""Cleaned-content builder for Liara's IaaS bundle page (evidence + hash)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.arvan_clean import TabContent, sha256_text  # noqa: E402
from collectors.liara_plans import parse_liara_plans  # noqa: E402


def clean_liara(page_html: str, source_url: str, tabs) -> dict[str, TabContent]:
    """Markdown of the parsed bundle plans — the skip-unchanged hash basis."""
    plans = parse_liara_plans(page_html)
    ipv4 = None
    try:
        from collectors.liara_plans import parse_ipv4_monthly

        ipv4 = parse_ipv4_monthly(page_html)
    except Exception:
        pass
    lines = [
        "# Liara IaaS (cloud server) bundles",
        f"Source: {source_url}",
        f"IPv4 monthly surcharge: {ipv4 or 'unknown'}",
        "",
        "| plan | monthly | hourly | RAM GB | vCPU | disk GB |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for p in plans:
        lines.append(f"| {p.name} | {p.monthly_toman} | {p.hourly_toman} | {p.ram_gb} | {p.vcpu} | {p.disk_gb} |")
    markdown = "\n".join(lines) + "\n"
    return {"plans": TabContent(tab="plans", markdown=markdown, rows=[], content_hash=sha256_text(markdown))}
