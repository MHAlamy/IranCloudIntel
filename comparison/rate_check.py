"""Verification of bundle prices against documented component rates, and
calculation of prices for configurations without a published bundle.

Deterministic by design (owner decision 2026-11-15): the arithmetic check runs
on every collection with zero tokens; the LLM's role is limited to interpreting
rate-table labels and diagnosing mismatches (review-only, never auto-accepted).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RATE_MAPPINGS_PATH = ROOT / "config" / "rate_mappings.yaml"

STORAGE_CLASS_LABELS = {
    "eco": "بلاک استوریج (Eco)",
    "hot_ssd": "بلاک استوریج (Hot-SSD)",
    "local": "بلاک استوریج (Local)",
    "warm": "بلاک استوریج (Warm)",
}


@dataclass
class ProviderRateMapping:
    provider_slug: str
    families: list[dict]
    calculated_price_factors: dict[str, Decimal]
    tier_generations: dict = field(default_factory=dict)

    def family_for(self, plan_name: str) -> dict | None:
        for family in self.families:
            if plan_name.lower().startswith(family["prefix"]):
                return family
        return None


def load_rate_mappings(path: Path = RATE_MAPPINGS_PATH) -> dict[str, ProviderRateMapping]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = {}
    for slug, cfg in data.items():
        result[slug] = ProviderRateMapping(
            provider_slug=slug,
            families=cfg["families"],
            calculated_price_factors={
                tier: Decimal(str(factor))
                for tier, factor in cfg["calculated_price_factors"].items()
            },
            tier_generations=dict(cfg.get("tier_generations", {})),
        )
    return result


@dataclass
class TierRates:
    """The published PAYG rates needed for one rate tier (monthly Toman)."""

    cpu_rate: Decimal           # per vCore
    ram_rate: Decimal           # per GB
    storage_rate: Decimal       # per GB for the default storage class
    ipv4_first: Decimal


def verify_bundle(
    plan_name: str, vcpu: int, ram_gb: Decimal, disk_gb: Decimal,
    price_in_toman: Decimal, rates: TierRates, mapping: ProviderRateMapping,
) -> tuple[str, str]:
    """Classify a bundle price against documented rates: verified | mismatch | review."""
    family = mapping.family_for(plan_name)
    if family is None:
        return "review", f"no rate-mapping family for plan {plan_name!r}"
    factor = Decimal(str(family["compute_factor"]))
    expected = (
        rates.ipv4_first
        + factor * (vcpu * rates.cpu_rate + ram_gb * rates.ram_rate)
        + disk_gb * rates.storage_rate
    )
    if expected == price_in_toman:
        return "verified", ""
    diff = price_in_toman - expected
    return (
        "mismatch",
        f"expected {expected} from documented rates (factor {factor}), actual {price_in_toman}, "
        f"difference {diff}",
    )


def calculated_price(
    tier: str, vcpu: int, ram_gb: Decimal, disk_gb: Decimal,
    rates: TierRates, mapping: ProviderRateMapping,
) -> Decimal:
    """Price for a configuration without a published bundle, from tier PAYG rates."""
    factor = mapping.calculated_price_factors.get(tier, Decimal("1"))
    return (
        rates.ipv4_first
        + factor * (vcpu * rates.cpu_rate + ram_gb * rates.ram_rate)
        + disk_gb * rates.storage_rate
    )
