"""LLM output contract for Object Storage price extraction
(price_gathering_guide.md 5.1 and 7: service-specific schemas — object-storage
pricing must not be forced into VM fields).

The LLM returns raw, source-grounded values only: verbatim price/currency/
period/capacity text, null for anything not shown. Normalization is
deterministic code (normalization/os_validate.py).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OS_SCHEMA_VERSION = "os-v1"


class LLMStoragePlanRow(BaseModel):
    """One Object Storage plan as extracted by the LLM from cleaned content."""

    model_config = ConfigDict(extra="forbid")

    plan_name: str = Field(min_length=1, description="Plan name exactly as shown, e.g. رشد")
    price_raw: str = Field(
        description=(
            "Price exactly as printed, e.g. '۱٬۸۰۰٬۰۰۰ تومان'; the literal "
            "free/quote marker ('رایگان', 'ثبت درخواست') when no price is shown"
        )
    )
    currency_raw: str = Field(default="", description="Currency label exactly as printed, e.g. 'تومان'")
    billing_period_raw: str = Field(default="", description="Billing period exactly as printed, e.g. 'ماهانه'")
    storage_raw: str | None = Field(default=None, description="Included storage exactly as printed, e.g. '۵۰۰ گیگابایت'")
    traffic_raw: str | None = Field(default=None, description="Included traffic exactly as printed, e.g. '۲ ترابایت'")
    requests_raw: str | None = Field(default=None, description="Included request allowance exactly as printed, e.g. '۲۰٬۰۰۰'")
    unlimited_raw: str | None = Field(
        default=None,
        description="Verbatim unlimited claim when present, e.g. 'فضای ذخیره‌سازی نامحدود'; null otherwise",
    )
    evidence: str = Field(min_length=1, description="Verbatim source excerpt supporting the row")


class NormalizedStoragePlanRow(BaseModel):
    """Deterministic normalization of an LLMStoragePlanRow; produced only by code."""

    model_config = ConfigDict(extra="forbid")

    plan_name: str
    plan_status: Literal["priced", "free", "quote_only"]
    price_value: Decimal | None
    currency: Literal["toman", "rial", "unknown"]
    price_in_toman: Decimal | None
    billing_period: Literal["monthly", "hourly", "unknown"]
    storage_included_gb: Decimal | None
    traffic_included_gb: Decimal | None
    requests_included: int | None
    storage_unlimited: bool
    traffic_unlimited: bool
    requests_unlimited: bool
    plan_url: str | None = None
    validation_status: Literal["valid", "suspect"]
    validation_issues: list[str] = Field(default_factory=list)
