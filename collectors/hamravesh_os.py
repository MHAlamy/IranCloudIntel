"""Deterministic extraction of Hamravesh Object Storage plans.

Page structure (verified 2026-11-15, after clicking the 'آبجکت استورج' pricing
menu item): a single attribute-matrix table — plans as columns, attributes as
rows:

    طرح           | پایه | رشد | حرفه‌ای | اختصاصی | سازمانی
    (price row)    ۳۷۵,۰۰۰ ... ثبت درخواست          <- no leading label cell
    فضای ذخیره‌سازی | ۱۰۰ GB | ۵۰۰ GB | ۵ TB | ۵۰ TB | (empty)
    ترافیک         | ۴۰۰ GB | ۲ TB  | ۲۰ TB | ۲۰۰ TB | (empty)
    هر GB فضای اضافه  | ۳,۰۰۰ تومان ...  | تماس بگیرید
    هر GB ترافیک اضافه | ۱,۲۰۰ تومان ... | تماس بگیرید

A missing price ('ثبت درخواست') is quote-only; empty capacity cells mean the
page does not state the value (recorded as unknown, never zero). The page
notes monthly prices are for 30-day (720-hour) months.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROW_LABELS = {
    "فضای ذخیره‌سازی": "storage",
    "ترافیک": "traffic",
    "هر GB فضای اضافه": "overage_storage",
    "هر GB ترافیک اضافه": "overage_traffic",
}
# ZWNJ-insensitive label matching
_LABEL_ALIASES = {
    "فضای ذخیره سازی": "storage",
    "هر GB فضای اضافه": "overage_storage",
    "هر GB ترافیک اضافه": "overage_traffic",
}


def _normalize_label(text: str) -> str:
    return text.replace("\u200c", " ").strip()


@dataclass
class OSPlan:
    plan_name: str
    price_raw: str  # verbatim: '۳۷۵,۰۰۰ تومان' or 'ثبت درخواست'
    storage_raw: str | None
    traffic_raw: str | None
    overage_storage_raw: str | None
    overage_traffic_raw: str | None
    evidence: str


def parse_hamravesh_os_plans(page_html: str) -> list[OSPlan]:
    soup = BeautifulSoup(page_html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        first_row = candidate.find("tr")
        if first_row is None:
            continue
        cells = first_row.find_all(["th", "td"])
        if cells and _normalize_label(cells[0].get_text(strip=True)) == "طرح":
            table = candidate
            break
    if table is None:
        raise ValueError("Hamravesh object-storage plan matrix not found on page")

    rows = table.find_all("tr")
    # plan names are source labels: kept verbatim (including ZWNJ)
    plan_names = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])[1:]]
    if not plan_names:
        raise ValueError("plan matrix header has no plan columns")

    plans: dict[str, dict[str, str | None]] = {name: {} for name in plan_names}
    for tr in rows[1:]:
        cells = tr.find_all(["th", "td"])
        texts = [c.get_text(" ", strip=True) for c in cells]
        if len(texts) == len(plan_names):
            # unlabeled price row (verified structure): aligns 1:1 with plan columns
            if not any(("تومان" in t) or ("ثبت درخواست" in t) for t in texts):
                continue  # not a price row; ignore unknown unlabeled rows
            for name, value in zip(plan_names, texts):
                plans[name]["price"] = value or None
            continue
        if len(texts) == len(plan_names) + 1:
            key = ROW_LABELS.get(texts[0]) or _LABEL_ALIASES.get(_normalize_label(texts[0]))
            if key is None:
                continue  # unknown attribute row — ignored, not guessed
            for name, value in zip(plan_names, texts[1:]):
                plans[name][key] = value or None
            continue
        # any other shape: ignore (decorative rows)

    result: list[OSPlan] = []
    for name in plan_names:
        data = plans[name]
        evidence_parts = [f"پلن {name}"]
        for key, value in data.items():
            if value:
                evidence_parts.append(f"{key}={value}")
        result.append(
            OSPlan(
                plan_name=name,
                price_raw=data.get("price") or "",
                storage_raw=data.get("storage"),
                traffic_raw=data.get("traffic"),
                overage_storage_raw=data.get("overage_storage"),
                overage_traffic_raw=data.get("overage_traffic"),
                evidence="؛ ".join(evidence_parts),
            )
        )
    return result


def build_hamravesh_os_markdown(page_html: str, source_url: str) -> str:
    """Deterministic cleaned content (used for evidence and content hashing)."""
    plans = parse_hamravesh_os_plans(page_html)
    lines = [
        f"# Hamravesh object-storage pricing\nSource: {source_url}\n",
        "| پلن | قیمت | فضای ذخیره‌سازی | ترافیک | هر GB فضای اضافه | هر GB ترافیک اضافه |",
        "|" + " --- |" * 6,
    ]
    for plan in plans:
        lines.append(
            f"| {plan.plan_name} | {plan.price_raw or '—'} | {plan.storage_raw or '—'} "
            f"| {plan.traffic_raw or '—'} | {plan.overage_storage_raw or '—'} "
            f"| {plan.overage_traffic_raw or '—'} |"
        )
    lines.append("")
    lines.append("هزینه ماهانه اعلام‌شده، برای ماه‌های ۳۰ روزه (۷۲۰ ساعته) است.")
    return "\n".join(lines) + "\n"
