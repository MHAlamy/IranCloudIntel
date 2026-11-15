"""Deterministic VM comparison: map raw collected plans onto the normalized
tiers and reference sizes (price_gathering_guide.md 6).

Owner decisions (2026-11-15), configurable in benchmarks.yaml:
- comparison covers Iranian regions only; all Iranian regions are treated as
  economically equivalent, but the actual region is always displayed;
- public IPv4 cost is NOT added for now (base price only).

Core rules:
- primary ranking requires an exact CPU/RAM match; disk may differ (shown
  with its actual size and difference from target);
- undersized plans never qualify as matches;
- when no exact CPU/RAM plan exists, the nearest larger plan may be shown
  separately, clearly marked approximate;
- multiple eligible plans rank cheapest-first;
- unknown tier labels go to review, never silently assigned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from config.loader import BenchmarksFile, TiersFile


def is_iranian_region(region: str, prefix: str = "ir-") -> bool:
    """Iranian region codes start with the configured prefix (e.g. 'ir-')."""
    return (region or "").lower().startswith(prefix)


@dataclass
class PlanView:
    """One collected plan prepared for comparison."""

    provider_slug: str
    plan_name: str
    tier: str  # normalized tier; 'review' sentinel when unmappable
    region: str
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    price_in_toman: Decimal
    observed_at: str
    validation_status: str


@dataclass
class Match:
    plan: PlanView
    match_type: str  # exact | disk_difference | approximate
    disk_difference_gb: Decimal | None = None  # actual - target


@dataclass
class SizeMatchResult:
    tier: str
    size_key: str
    primary: list[Match] = field(default_factory=list)       # ranked cheapest-first
    approximate: list[Match] = field(default_factory=list)   # nearest larger, per provider
    review_flags: list[str] = field(default_factory=list)
    no_match_reasons: list[str] = field(default_factory=list)


class VMMatcher:
    def __init__(self, benchmarks: BenchmarksFile, tiers: TiersFile):
        self._benchmarks = benchmarks.vm
        self._tiers = tiers.vm
        self._region_prefix = self._benchmarks.regions.iranian_prefix
        self._region_scope = self._benchmarks.regions.scope

    def normalize_tier(self, provider_slug: str, provider_tier_raw: str) -> str:
        """Map a provider-native tier label to a normalized tier; 'review' if unmappable."""
        entry = self._tiers.providers.get(provider_slug)
        if entry is None:
            return "review"
        raw = (provider_tier_raw or "").strip().lower()
        if raw in entry.aliases:
            return entry.aliases[raw]
        if entry.default:
            return entry.default
        return "review"

    def _dedupe_iranian_regions(self, plans: list[PlanView], review_flags: list[str]) -> list[PlanView]:
        """Same plan name in several Iranian regions: keep cheapest, flag price divergence."""
        groups: dict[tuple, list[PlanView]] = {}
        for plan in plans:
            groups.setdefault(
                (plan.provider_slug, plan.plan_name, plan.tier, plan.vcpu, plan.ram_gb, plan.disk_gb),
                [],
            ).append(plan)
        result: list[PlanView] = []
        for group in groups.values():
            if len({p.price_in_toman for p in group}) > 1:
                review_flags.append(
                    f"same plan priced differently across Iranian regions: "
                    f"{group[0].provider_slug}/{group[0].plan_name}"
                )
            result.append(min(group, key=lambda p: p.price_in_toman))
        return result

    def match_size(
        self, plans: list[PlanView], tier: str, size_key: str, region_scope: str | None = None,
    ) -> SizeMatchResult:
        """Match one reference size within one normalized tier."""
        size = self._benchmarks.sizes[size_key]
        target_vcpu, target_ram, target_disk = size.vcpu, size.ram_gb, size.disk_gb
        result = SizeMatchResult(tier=tier, size_key=size_key)

        tier_plans = [p for p in plans if p.tier == tier]
        for plan in plans:
            if plan.tier == "review":
                result.review_flags.append(
                    f"unmapped tier label: {plan.provider_slug}/{plan.plan_name}"
                )

        scope = region_scope if region_scope is not None else self._region_scope
        if scope == "iran":
            scoped = [p for p in tier_plans if is_iranian_region(p.region, self._region_prefix)]
        else:
            scoped = list(tier_plans)
        scoped = self._dedupe_iranian_regions(scoped, result.review_flags)

        # Primary ranking: exact CPU/RAM only; disk may differ from the target.
        exact_cpu_ram = [p for p in scoped if p.vcpu == target_vcpu and p.ram_gb == target_ram]
        for plan in exact_cpu_ram:
            diff = plan.disk_gb - target_disk
            result.primary.append(
                Match(
                    plan=plan,
                    match_type="exact" if diff == 0 else "disk_difference",
                    disk_difference_gb=diff,
                )
            )
        result.primary.sort(
            key=lambda m: (m.match_type != "exact", abs(m.disk_difference_gb or 0), m.plan.price_in_toman)
        )

        if not result.primary:
            larger = [p for p in scoped if p.vcpu > target_vcpu or p.ram_gb > target_ram]
            if larger:
                cheapest_by_provider: dict[str, PlanView] = {}
                for plan in larger:
                    current = cheapest_by_provider.get(plan.provider_slug)
                    if current is None or plan.price_in_toman < current.price_in_toman:
                        cheapest_by_provider[plan.provider_slug] = plan
                result.approximate = [
                    Match(plan=plan, match_type="approximate")
                    for plan in sorted(cheapest_by_provider.values(), key=lambda p: p.price_in_toman)
                ]
            elif scoped:
                result.no_match_reasons.append(
                    f"no {tier} plan with >= {target_vcpu} vCPU / {target_ram} GB RAM in scope"
                )

        if not scoped:
            if not tier_plans:
                result.no_match_reasons.append(f"no collected plans for tier {tier}")
            else:
                result.no_match_reasons.append(
                    f"no {tier} plans in Iranian regions (foreign-region plans excluded by scope)"
                )
        return result
