"""Deterministic validation and normalization of Object Storage plan rows.

Same rules as normalization/validate.py (VM): the LLM never computes, unknown
is distinct from zero, issues are flagged instead of silently accepted
(price_gathering_guide.md 5.2 and 7). Object-storage specifics:
- capacities parsed from verbatim text ('۵۰۰ گیگابایت', '۵ ترابایت') with an
  explicit, configurable TB→GB factor;
- plan_status: priced | free | quote_only — a free plan's zero price is a
  source claim (valid), unlike a missing price.
"""

from __future__ import annotations

from decimal import Decimal

from extractors.os_schema import LLMStoragePlanRow, NormalizedStoragePlanRow
from normalization.persian import (
    normalize_billing_period,
    normalize_currency,
    parse_price,
    toman_from_rial,
)

_QUOTE_MARKERS = ("ثبت درخواست", "تماس بگیرید")
_FREE_MARKERS = ("رایگان",)
_UNLIMITED_MARKERS = ("نامحدود",)


def parse_capacity_gb(text: str | None, tb_to_gb: int = 1024) -> Decimal | None:
    """Parse '۵۰۰ گیگابایت' / '۵ ترابایت' / '500 GB' into GB.

    Returns None for None/empty/'نامحدود' (unlimited is a flag, not a number).
    Raises ValueError only on non-empty text that holds no parsable capacity,
    so callers can flag it rather than silently dropping it.
    """
    if text is None:
        return None
    from normalization.persian import to_latin_digits

    latin = to_latin_digits(text).strip()
    if not latin:
        return None
    if any(marker in text for marker in _UNLIMITED_MARKERS):
        return None
    # unit detection before digit cleanup (unit words contain no digits)
    lowered = latin.lower()
    if "ترابایت" in text or "tb" in lowered or "tib" in lowered:
        factor = Decimal(tb_to_gb)
    elif "گیگابایت" in text or "gb" in lowered or "gib" in lowered:
        factor = Decimal(1)
    elif "مگابایت" in text or "mb" in lowered:
        factor = Decimal(1) / Decimal(1024)
    else:
        raise ValueError(f"unrecognized capacity unit in {text!r}")
    number = parse_price(text)
    return number * factor


def parse_requests(text: str | None) -> int | None:
    """Parse '۲۰٬۰۰۰' into 20000; None for None/empty/'نامحدود'."""
    if text is None or not text.strip():
        return None
    if any(marker in text for marker in _UNLIMITED_MARKERS):
        return None
    return int(parse_price(text))


def _unlimited_flags(unlimited_raw: str | None) -> tuple[bool, bool, bool]:
    phrase = unlimited_raw or ""
    storage = "ذخیره‌سازی" in phrase and any(m in phrase for m in _UNLIMITED_MARKERS)
    traffic = "ترافیک" in phrase and any(m in phrase for m in _UNLIMITED_MARKERS)
    requests = "درخواست" in phrase and any(m in phrase for m in _UNLIMITED_MARKERS)
    return storage, traffic, requests


def normalize_os_row(
    row: LLMStoragePlanRow, tb_to_gb: int = 1024, plan_url: str | None = None
) -> NormalizedStoragePlanRow:
    issues: list[str] = []

    plan_status: str
    price_value: Decimal | None
    currency = "unknown"
    price_in_toman: Decimal | None
    billing_period = normalize_billing_period(row.billing_period_raw)

    price_text = (row.price_raw or "").strip()
    if any(marker in price_text for marker in _QUOTE_MARKERS):
        plan_status, price_value, price_in_toman = "quote_only", None, None
        billing_period = "monthly" if billing_period == "unknown" else billing_period
    elif any(marker in price_text for marker in _FREE_MARKERS):
        plan_status, price_value, price_in_toman = "free", Decimal("0"), Decimal("0")
    else:
        plan_status = "priced"
        price_in_toman = None
        try:
            price_value = parse_price(price_text)
        except ValueError as exc:
            price_value = None
            issues.append(f"price unparsable: {exc}")
        currency = normalize_currency(row.currency_raw or price_text)
        if currency == "unknown":
            issues.append(f"unrecognized currency {row.currency_raw!r}")
        elif currency == "toman":
            price_in_toman = price_value
        else:  # rial: convert only when explicitly stated
            price_in_toman = toman_from_rial(price_value) if price_value is not None else None
        if price_value is not None and price_value < 0:
            issues.append("price is negative")
        if billing_period == "unknown":
            issues.append(f"unrecognized billing period {row.billing_period_raw!r}")

    storage_unlimited, traffic_unlimited, requests_unlimited = _unlimited_flags(row.unlimited_raw)
    if row.storage_raw and any(m in row.storage_raw for m in _UNLIMITED_MARKERS):
        storage_unlimited = True
    if row.traffic_raw and any(m in row.traffic_raw for m in _UNLIMITED_MARKERS):
        traffic_unlimited = True
    if row.requests_raw and any(m in row.requests_raw for m in _UNLIMITED_MARKERS):
        requests_unlimited = True

    storage_gb: Decimal | None
    try:
        storage_gb = parse_capacity_gb(row.storage_raw, tb_to_gb)
    except ValueError as exc:
        storage_gb = None
        issues.append(f"storage capacity unparsable: {exc}")
    traffic_gb: Decimal | None
    try:
        traffic_gb = parse_capacity_gb(row.traffic_raw, tb_to_gb)
    except ValueError as exc:
        traffic_gb = None
        issues.append(f"traffic capacity unparsable: {exc}")
    try:
        requests_included = parse_requests(row.requests_raw)
    except ValueError as exc:
        requests_included = None
        issues.append(f"request allowance unparsable: {exc}")

    if plan_status in ("priced", "free") and storage_gb is None and not storage_unlimited \
            and traffic_gb is None and not traffic_unlimited:
        issues.append("no capacity information (storage and traffic both unknown)")

    return NormalizedStoragePlanRow(
        plan_name=row.plan_name,
        plan_status=plan_status,  # type: ignore[arg-type]
        price_value=price_value,
        currency=currency,  # type: ignore[arg-type]
        price_in_toman=price_in_toman,
        billing_period=billing_period,  # type: ignore[arg-type]
        storage_included_gb=storage_gb,
        traffic_included_gb=traffic_gb,
        requests_included=requests_included,
        storage_unlimited=storage_unlimited,
        traffic_unlimited=traffic_unlimited,
        requests_unlimited=requests_unlimited,
        plan_url=plan_url,
        validation_status="valid" if not issues else "suspect",
        validation_issues=issues,
    )
