"""LLM output contract for VM price extraction (price_gathering_guide.md 5.1).

The LLM returns raw, source-grounded values only: it must not normalize,
convert currencies, compute equivalents or invent values. Normalization is
deterministic code (normalization/).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "vm-v2"


class LLMPlanRow(BaseModel):
    """One plan row as extracted by the LLM from cleaned page content."""

    model_config = ConfigDict(extra="forbid")

    plan_name: str = Field(min_length=1, description="Plan name exactly as shown, e.g. eco-small4")
    provider_tier_raw: str = Field(description="Tab/section label exactly as shown, e.g. basic")
    region: str | None = None
    vcpu: int | None = None
    ram_gb: float | None = None
    disk_gb: float | None = None
    disk_type: str | None = None
    price_raw: str = Field(description="Price exactly as printed in the source, e.g. '۹۹۷,۷۴۰'")
    currency_raw: str = Field(description="Currency label exactly as printed, e.g. 'تومان'")
    billing_period_raw: str = Field(description="Billing period exactly as printed, e.g. 'ماهانه'")
    evidence: str = Field(min_length=1, description="Verbatim source excerpt supporting the row")

    @field_validator("vcpu", "ram_gb", "disk_gb")
    @classmethod
    def _nonnegative(cls, v, info):
        if v is not None and v < 0:
            raise ValueError(f"{info.field_name} must be nonnegative")
        return v


class NormalizedPlanRow(BaseModel):
    """Deterministic normalization of an LLMPlanRow; produced only by code."""

    model_config = ConfigDict(extra="forbid")

    plan_name: str
    provider_tier_raw: str
    region: str | None
    vcpu: int | None
    ram_gb: float | None
    disk_gb: float | None
    disk_type: str | None
    conversion_hours: int | None = None
    price_value: Decimal
    currency: Literal["toman", "rial", "unknown"]
    price_in_toman: Decimal | None = None  # set only when source currency is explicit
    billing_period: Literal["monthly", "hourly", "unknown"]
    pricing_type: Literal["fixed_bundle", "configurable_quote", "resource_rate", "other"]
    plan_url: str | None = None
    validation_status: Literal["valid", "suspect"]
    validation_issues: list[str] = Field(default_factory=list)
