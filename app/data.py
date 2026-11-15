"""View-model assembly for the dashboard: turns stored observations and rates
into the comparison view (price_gathering_guide.md 8).

Basis labels shown to the user:
- published   (منتشرشده): an actual bundle price from the provider
- calculated  (محاسبه‌شده): computed from the provider's documented rates
- approximate (تقریبی): nearest larger plan, clearly marked
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comparison.matching import PlanView, VMMatcher  # noqa: E402
from comparison.rate_check import (  # noqa: E402
    ProviderRateMapping,
    calculated_price,
    load_rate_mappings,
)
from config.loader import load_benchmarks, load_providers, load_tiers  # noqa: E402
from storage.repository import Repository  # noqa: E402
from util.jalali import format_jalali  # noqa: E402

TIER_LABELS_FA = {"economy": "اقتصادی", "standard": "استاندارد", "premium": "پرمیوم"}
SIZE_LABELS_FA = {
    "small": "کوچک",
    "medium": "متوسط",
    "large": "بزرگ",
    "very_large": "خیلی بزرگ",
}
BASIS_LABELS_FA = {
    "published": "منتشرشده",
    "calculated": "محاسبه‌شده",
    "approximate": "تقریبی",
    "missing": "در دسترس نیست",
}
VERIFICATION_LABELS_FA = {
    "verified": "تأیید‌شده با نرخ‌ها",
    "mismatch": "ناهمخوان با نرخ‌ها",
    "review": "نیازمند بررسی",
    "not_applicable": "—",
}


@dataclass
class VmRow:
    provider_name: str
    plan_name: str
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    price_in_toman: Decimal | None
    basis: str  # published | calculated | approximate | missing
    rate_verification: str
    observed_at: str
    offering_id: int | None
    notes: list[str] = field(default_factory=list)


def build_plan_views(repo: Repository, matcher: VMMatcher) -> list[PlanView]:
    plans: list[PlanView] = []
    for row in repo.latest_observations(service_type="vm"):
        plans.append(
            PlanView(
                provider_slug=row["provider_slug"],
                plan_name=row["plan_name"],
                tier=matcher.normalize_tier(row["provider_slug"], row["provider_tier_raw"]),
                region=row["region"] or "",
                vcpu=row["vcpu"] or 0,
                ram_gb=Decimal(str(row["ram_gb"] or 0)),
                disk_gb=Decimal(str(row["disk_gb"] or 0)),
                price_in_toman=Decimal(row["price_in_toman"]),
                observed_at=row["observed_at"],
                validation_status=row["validation_status"],
            )
        )
    return plans


def _provider_rate_context(repo: Repository, provider_id: int, slug: str, mapping: ProviderRateMapping):
    """Return a rates lookup helper for calculated prices, or None."""
    rows = repo.latest_rates(provider_id, region="iran")
    by_key = {(r["category"], r["unit"], r["tier_label"]): Decimal(r["amount_toman"]) for r in rows}

    def get(category: str, unit: str, tier_label: str) -> Decimal | None:
        return by_key.get((category, unit, tier_label))

    ipv4 = next((v for (cat, _, label), v in by_key.items() if cat == "ipv4" and "اول" in label), None)
    if ipv4 is None:
        return None

    tier_names = {"economy": "Basic", "standard": "Standard", "premium": "Premium"}
    storage_label = "بلاک استوریج (Eco)"

    def calculated(tier: str, vcpu: int, ram_gb: Decimal, disk_gb: Decimal) -> Decimal | None:
        cpu = get("cpu", "هر vCore", tier_names.get(tier, ""))
        ram = get("ram", "هر گیگابایت", tier_names.get(tier, ""))
        storage = get("storage", "هر گیگابایت", storage_label)
        if cpu is None or ram is None or storage is None:
            return None
        return calculated_price(tier, vcpu, ram_gb, disk_gb,
                                type("R", (), {"cpu_rate": cpu, "ram_rate": ram,
                                               "storage_rate": storage, "ipv4_first": ipv4})(),
                                mapping)

    return calculated


def build_vm_view(repo: Repository, tier: str, size_key: str) -> dict:
    benchmarks = load_benchmarks()
    tiers = load_tiers()
    providers_file = load_providers()
    matcher = VMMatcher(benchmarks, tiers)
    rate_mappings = load_rate_mappings()

    plans = build_plan_views(repo, matcher)
    result = matcher.match_size(plans, tier, size_key)

    size = benchmarks.vm.sizes[size_key]
    view: dict = {
        "tier": tier,
        "size": size_key,
        "tier_fa": TIER_LABELS_FA[tier],
        "size_fa": SIZE_LABELS_FA[size_key],
        "target": {"vcpu": size.vcpu, "ram_gb": size.ram_gb, "disk_gb": size.disk_gb},
        "rows": [],
        "review_flags": result.review_flags,
        "no_match_reasons": result.no_match_reasons,
    }

    provider_names = {p.slug: p.name for p in providers_file.providers}
    collected_providers = {p.provider_slug for p in plans}
    latest_observed_by_provider: dict[str, str] = {}
    for p in plans:
        if p.observed_at > latest_observed_by_provider.get(p.provider_slug, ""):
            latest_observed_by_provider[p.provider_slug] = p.observed_at

    primary_by_provider: dict[str, list] = {}
    for match in result.primary:
        primary_by_provider.setdefault(match.plan.provider_slug, []).append(match)
    approximate_by_provider: dict[str, list] = {}
    for match in result.approximate:
        approximate_by_provider.setdefault(match.plan.provider_slug, []).append(match)

    def add_row(provider_slug: str, price: Decimal | None, basis: str, *,
                plan_name: str = "", vcpu: int | None = None,
                ram_gb: Decimal | None = None, disk_gb: Decimal | None = None,
                rate_verification: str = "not_applicable", observed_at: str = "",
                offering_id: int | None = None, notes: list[str] | None = None):
        view["rows"].append(VmRow(
            provider_name=provider_names.get(provider_slug, provider_slug),
            plan_name=plan_name, vcpu=vcpu or 0, ram_gb=ram_gb or Decimal(0),
            disk_gb=disk_gb or Decimal(0), price_in_toman=price, basis=basis,
            rate_verification=rate_verification, observed_at=observed_at,
            offering_id=offering_id, notes=notes or [],
        ))

    for slug in sorted(set(collected_providers) | {p.slug for p in providers_file.providers}):
        # 1) Published bundle exactly matching the reference size (CPU/RAM/disk)
        if slug in primary_by_provider:
            for match in primary_by_provider[slug]:
                p = match.plan
                add_row(
                    slug, p.price_in_toman, "published", plan_name=p.plan_name,
                    vcpu=p.vcpu, ram_gb=p.ram_gb, disk_gb=p.disk_gb,
                    observed_at=p.observed_at, offering_id=_offering_id(repo, slug, p),
                )
            continue

        if slug not in collected_providers:
            add_row(slug, None, "missing", notes=["هنوز گردآوری نشده"])
            continue

        # 2) Calculated from the provider's documented rates (baseline config)
        calculated_price = None
        if slug in rate_mappings:
            provider_id = _provider_id(repo, slug)
            calculated_fn = (
                _provider_rate_context(repo, provider_id, slug, rate_mappings[slug])
                if provider_id else None
            )
            if calculated_fn is not None:
                calculated_price = calculated_fn(
                    tier, size.vcpu, Decimal(size.ram_gb), Decimal(size.disk_gb)
                )
        if calculated_price is not None:
            add_row(
                slug, calculated_price, "calculated",
                plan_name=f"پیکربندی {SIZE_LABELS_FA[size_key]} {TIER_LABELS_FA[tier]}",
                vcpu=size.vcpu, ram_gb=Decimal(size.ram_gb), disk_gb=Decimal(size.disk_gb),
                observed_at=latest_observed_by_provider.get(slug, ""),
                notes=["محاسبه‌شده از نرخ‌های اعلامی تأمین‌کننده (شامل IPv4)؛ فرض: تخفیف خانواده‌ی بسته‌ها اعمال شده است"],
            )
            continue

        # 3) No rates available: nearest larger published bundle, marked approximate
        if slug in approximate_by_provider:
            for match in approximate_by_provider[slug]:
                p = match.plan
                add_row(
                    slug, p.price_in_toman, "approximate", plan_name=p.plan_name,
                    vcpu=p.vcpu, ram_gb=p.ram_gb, disk_gb=p.disk_gb,
                    observed_at=p.observed_at, offering_id=_offering_id(repo, slug, p),
                    notes=["بسته‌ی بزرگ‌تر از مرجع؛ به‌عنوان تقریبی نمایش داده می‌شود"],
                )
            continue

        # 4) Collected but nothing usable for this size
        add_row(slug, None, "missing", notes=["پلن منطبق یا قابل‌محاسبه برای این اندازه یافت نشد"])

    # Sort: published cheapest-first, then calculated, then approximate, then missing
    order = {"published": 0, "calculated": 1, "approximate": 2, "missing": 3}
    view["rows"].sort(key=lambda r: (order[r.basis], r.price_in_toman if r.price_in_toman is not None else Decimal("999999999999")))
    return view


def _provider_id(repo: Repository, slug: str) -> int | None:
    row = repo._connection.execute("SELECT id FROM providers WHERE slug=?", (slug,)).fetchone()
    return int(row["id"]) if row else None


def _offering_id(repo: Repository, slug: str, plan: PlanView) -> int | None:
    row = repo._connection.execute(
        """SELECT off.id FROM offerings off JOIN providers p ON p.id=off.provider_id
           WHERE p.slug=? AND off.plan_name=? AND off.region=?""",
        (slug, plan.plan_name, plan.region),
    ).fetchone()
    return int(row["id"]) if row else None


def build_status_view(repo: Repository) -> dict:
    sources = []
    for source in repo.list_sources():
        runs = repo.source_runs(source["id"])
        sources.append({
            "provider_name": source["provider_name"],
            "provider_slug": source["provider_slug"],
            "service_type": source["service_type"],
            "url": source["url"],
            "enabled": bool(source["enabled"]) if "enabled" in source.keys() else True,
            "rates_stored": repo.rate_count(_provider_id(repo, source["provider_slug"]) or 0),
            "runs": [
                {
                    "status": r["status"],
                    "started_jalali": format_jalali(r["started_at"]),
                    "tokens": f"{r['prompt_tokens']}/{r['completion_tokens']}",
                    "error": r["error"],
                }
                for r in runs
            ],
        })
    return {"sources": sources}
