"""Deterministic validation and normalization of LLM-extracted plan rows.

The LLM never computes: this module turns raw source-grounded values into
normalized observations, flags issues instead of silently rejecting, and keeps
unknown distinct from zero (price_gathering_guide.md 5.2).
"""

from __future__ import annotations

from decimal import Decimal

from extractors.schema import LLMPlanRow, NormalizedPlanRow
from normalization.persian import (
    normalize_billing_period,
    normalize_currency,
    parse_price,
    toman_from_rial,
)


def normalize_llm_row(row: LLMPlanRow, plan_url: str | None = None, monthly_hours: int = 730) -> NormalizedPlanRow:
    issues: list[str] = []

    # Price: parse deterministically from the verbatim source text
    try:
        price_value = parse_price(row.price_raw)
    except ValueError as exc:
        price_value = Decimal("0")
        issues.append(f"price unparsable: {exc}")

    currency = normalize_currency(row.currency_raw)
    if currency == "unknown":
        issues.append(f"unrecognized currency {row.currency_raw!r}")

    price_in_toman: Decimal | None = None
    if currency == "toman":
        price_in_toman = price_value
    elif currency == "rial":
        # Convert only when the source explicitly states Rial (10 Rial = 1 Toman)
        price_in_toman = toman_from_rial(price_value)
    if price_value <= 0:
        issues.append("price is zero or negative; unknown/absent must not be encoded as zero")

    billing_period = normalize_billing_period(row.billing_period_raw)
    if billing_period == "unknown":
        issues.append(f"unrecognized billing period {row.billing_period_raw!r}")

    if monthly_hours <= 0:
        raise ValueError('monthly_hours must be positive')
    if billing_period == 'hourly' and price_in_toman is not None:
        price_in_toman *= Decimal(monthly_hours)
        billing_period = 'monthly'
    if billing_period == 'unknown':
        price_in_toman = None

    if row.vcpu is None or row.ram_gb is None or row.disk_gb is None:
        issues.append("missing resource specification (vcpu/ram/disk)")

    return NormalizedPlanRow(
        plan_name=row.plan_name,
        provider_tier_raw=row.provider_tier_raw,
        region=row.region,
        vcpu=row.vcpu,
        ram_gb=row.ram_gb,
        disk_gb=row.disk_gb,
        disk_type=row.disk_type,
        conversion_hours=monthly_hours if normalize_billing_period(row.billing_period_raw) == "hourly" else None,
        price_value=price_value,
        currency=currency,  # type: ignore[arg-type]
        price_in_toman=price_in_toman,
        billing_period=billing_period,  # type: ignore[arg-type]
        pricing_type="fixed_bundle",
        plan_url=plan_url,
        validation_status="valid" if not issues else "suspect",
        validation_issues=issues,
    )
