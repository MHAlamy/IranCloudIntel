"""Pure monthly-cost rules for the Managed Kubernetes (KaaS) comparison.

Visualization code must not contain pricing formulas: this module owns the
worker-resource arithmetic, the configured management-fee ladders and the
Sotoon node-count transition. All amounts are monthly Toman.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

IRR_PER_TOMAN = Decimal("10")


@dataclass(frozen=True)
class FeeTier:
    """Half-open [lower, upper) range; `upper=None` means open-ended."""

    lower: int
    upper: int | None
    fee_toman: Decimal


@dataclass(frozen=True)
class KaasTariffs:
    cpu_toman: Decimal
    ram_toman: Decimal
    storage_toman: Decimal
    fee_tiers: tuple[FeeTier, ...] = ()
    standard_fee_toman: Decimal | None = None
    premium_fee_toman: Decimal | None = None
    standard_node_fee_toman: Decimal | None = None
    premium_node_fee_toman: Decimal | None = None


@dataclass(frozen=True)
class KaasCost:
    management_toman: Decimal | None
    worker_toman: Decimal
    control_plane_toman: Decimal

    @property
    def total_toman(self) -> Decimal | None:
        """Unknown unless the provider published a fee for this cluster size."""
        if self.management_toman is None:
            return None
        return self.management_toman + self.worker_toman + self.control_plane_toman


def irr_to_toman(irr: int | Decimal | str) -> Decimal:
    """The Sotoon price list prints IRR; the dashboard's unit is Toman."""
    return Decimal(irr) / IRR_PER_TOMAN


def parse_fee_tier_label(label: str) -> tuple[int, int | None] | None:
    """Parse a stored ladder label such as `0-200` or `1500-`."""
    lower_text, separator, upper_text = (label or "").partition("-")
    if not separator or not lower_text.strip().isdigit():
        return None
    lower = int(lower_text)
    upper = int(upper_text) if upper_text.strip().isdigit() else None
    return lower, upper


def fee_for(value: int, tiers: tuple[FeeTier, ...]) -> Decimal | None:
    """Management fee for one ladder metric; None when the ladder ends first."""
    matches = [
        tier for tier in tiers
        if value >= tier.lower and (tier.upper is None or value < tier.upper)
    ]
    if not matches:
        return None
    return max(matches, key=lambda tier: tier.lower).fee_toman


def worker_cost(
    vcpu: int, ram_gb: Decimal, disk_gb: Decimal, tariffs: KaasTariffs,
) -> Decimal:
    return (
        Decimal(vcpu) * tariffs.cpu_toman
        + ram_gb * tariffs.ram_toman
        + disk_gb * tariffs.storage_toman
    )


def hamravesh_cost(
    total_vcpu: int, ram_gb: Decimal, disk_gb: Decimal,
    tariffs: KaasTariffs, control_plane_toman: Decimal,
) -> KaasCost:
    """Both Hamravesh offerings key their configured fee ladder on total vCPU."""
    return KaasCost(
        management_toman=fee_for(total_vcpu, tariffs.fee_tiers),
        worker_toman=worker_cost(total_vcpu, ram_gb, disk_gb, tariffs),
        control_plane_toman=control_plane_toman,
    )


def kubit_cost(
    total_vcpu: int, ram_gb: Decimal, disk_gb: Decimal,
    tariffs: KaasTariffs, control_plane_toman: Decimal,
) -> KaasCost:
    """Kubit's licence ladder uses P = 2 × vCPU + RAM(GB)."""
    p_score = int(Decimal(2) * total_vcpu + ram_gb)
    return KaasCost(
        management_toman=fee_for(p_score, tariffs.fee_tiers),
        worker_toman=worker_cost(total_vcpu, ram_gb, disk_gb, tariffs),
        control_plane_toman=control_plane_toman,
    )


def sotoon_cost(
    total_vcpu: int, nodes: int, ram_gb: Decimal, disk_gb: Decimal,
    tariffs: KaasTariffs, control_plane_toman: Decimal, premium_min_nodes: int,
) -> KaasCost:
    """Cluster subscription + per-node management fee, standard or premium."""
    premium = nodes >= premium_min_nodes
    base_fee = tariffs.premium_fee_toman if premium else tariffs.standard_fee_toman
    node_fee = (
        tariffs.premium_node_fee_toman if premium
        else tariffs.standard_node_fee_toman
    )
    management = (
        base_fee + Decimal(nodes) * node_fee
        if base_fee is not None and node_fee is not None
        else None
    )
    return KaasCost(
        management_toman=management,
        worker_toman=worker_cost(total_vcpu, ram_gb, disk_gb, tariffs),
        control_plane_toman=control_plane_toman,
    )
