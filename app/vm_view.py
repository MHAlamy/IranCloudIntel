"""VM comparison view assembly."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


from comparison.matching import PlanView, VMMatcher
from comparison.rate_check import (
    ProviderRateMapping,
    calculated_price,
    load_rate_mappings,
)
from config.loader import load_analyst_facts
from config.loader import load_benchmarks, load_providers, load_tiers
from util.format import format_number, format_toman
from util.jalali import format_jalali
from storage.repository import Repository

from app.view_common import _provider_id, _offering_id

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
    "proposed": "پیشنهادی / منتشرنشده",
    "missing": "در دسترس نیست",
}
VERIFICATION_LABELS_FA = {
    "verified": "تأیید‌شده با نرخ‌ها",
    "mismatch": "ناهمخوان با نرخ‌ها",
    "review": "نیازمند بررسی",
    "not_applicable": "—",
}


@dataclass
class _Rates:
    """Minimal rate bundle consumed by comparison.rate_check.calculated_price."""

    cpu_rate: Decimal
    ram_rate: Decimal
    storage_rate: Decimal
    ipv4_first: Decimal


@dataclass
class VmRow:
    provider_slug: str
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
    provenance: str = "live"  # live | manual
    source_document: str = ""
    valid_until: str = ""
    disk_type: str = ""


def build_plan_views(repo: Repository, matcher: VMMatcher) -> list[PlanView]:
    plans: list[PlanView] = []
    for row in repo.latest_observations(service_type="vm"):
        if row["billing_period"] != "monthly":
            continue  # legacy hourly observations require recollection
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
                provider_tier_raw=row["provider_tier_raw"] or "",
                disk_type=row["disk_type"] or "",
                provenance="manual" if row["collection_method"] == "manual" else "live",
                source_document=row["source_document"] or "",
                valid_until=row["valid_until"] or "",
            )
        )
    return plans


def _manual_source_note(source_document: str, valid_until: str) -> str:
    """Provenance line for a price imported from an offline document."""
    parts = []
    if source_document:
        parts.append(f"منبع دستی: {source_document}")
    if valid_until:
        parts.append(f"معتبر تا {format_jalali(valid_until, with_time=False)}")
    return " · ".join(parts)


def _manual_calculation_note(
    vcpu: int, disk_gb: Decimal, allocation: str, disk_type: str,
) -> str:
    kind = "اختصاصی" if allocation == "dedicated" else "اشتراکی"
    disk = disk_type or "دیسک"
    return (
        f"محاسبه: {format_number(vcpu)} برابر بسته‌ی ۱ vCPU + ۲ GB {kind} "
        f"+ {format_number(disk_gb)} گیگابایت {disk}"
    )


def _provider_rate_context(repo: Repository, provider_id: int, slug: str, mapping: ProviderRateMapping):
    """Return a calculated(tier, vcpu, ram_gb, disk_gb) -> Decimal | None closure
    for a provider, or None when its rates are unusable."""
    rows = repo.latest_rates(provider_id, region="iran")
    by_key = {(r["category"], r["unit"], r["tier_label"]): Decimal(r["amount_toman"]) for r in rows}

    def get(category: str, unit: str, tier_label: str) -> Decimal | None:
        return by_key.get((category, unit, tier_label))

    if slug == "arvan":
        ipv4 = next(
            (v for (cat, _, label), v in by_key.items() if cat == "ipv4" and "اول" in label),
            None,
        )
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
                                    _Rates(cpu, ram, storage, ipv4), mapping)

        return calculated

    if slug == "kubit":
        # Pure rate-based provider: every price is calculated. gen-3 → Economy,
        # gen-4 → Standard, no premium (owner decision 2026-11-15).
        ipv4 = get("ipv4", "هر آدرس", "internet")
        if ipv4 is None:
            return None
        generations = mapping.tier_generations or {"economy": "gen-3", "standard": "gen-4"}

        def calculated(tier: str, vcpu: int, ram_gb: Decimal, disk_gb: Decimal) -> Decimal | None:
            gen = generations.get(tier)
            if not gen:
                return None  # no offering in this tier
            cpu = get("cpu", "هر vCPU", gen)
            ram = get("ram", "هر گیگابایت", gen)
            storage = get("storage", "هر گیگابایت", "")
            if cpu is None or ram is None or storage is None:
                return None
            return calculated_price(tier, vcpu, ram_gb, disk_gb,
                                    _Rates(cpu, ram, storage, ipv4), mapping)

        return calculated

    return None


def build_vm_view(repo: Repository, tier: str, size_key: str) -> dict:
    benchmarks = load_benchmarks()
    tiers = load_tiers()
    providers_file = load_providers()
    matcher = VMMatcher(benchmarks, tiers)
    rate_mappings = load_rate_mappings()
    provider_order = {p.slug: i for i, p in enumerate(providers_file.providers)}

    plans = build_plan_views(repo, matcher)
    result = matcher.match_size(plans, tier, size_key)
    facts = load_analyst_facts()
    parspack_facts = facts.get("parspack")

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
    # providers whose rates have been collected count as collected even
    # without bundle observations (rates-only providers, e.g. Kubit)
    rates_providers = {
        row["slug"]
        for row in repo._connection.execute(
            "SELECT DISTINCT p.slug AS slug FROM published_resource_rates r JOIN providers p ON p.id = r.provider_id"
        ).fetchall()
    }
    latest_observed_by_provider: dict[str, str] = {}
    for p in plans:
        if p.observed_at > latest_observed_by_provider.get(p.provider_slug, ""):
            latest_observed_by_provider[p.provider_slug] = p.observed_at
    # rates-only providers (e.g. Kubit) have no bundle observations; their
    # "last checked" comes from the latest rate collection run
    for row in repo._connection.execute(
        """SELECT p.slug AS slug, MAX(r.observed_at) AS m
           FROM published_resource_rates r JOIN providers p ON p.id = r.provider_id
           GROUP BY p.slug"""
    ).fetchall():
        if row["m"] and row["m"] > latest_observed_by_provider.get(row["slug"], ""):
            latest_observed_by_provider[row["slug"]] = row["m"]

    primary_by_provider: dict[str, list] = {}
    for match in result.primary:
        primary_by_provider.setdefault(match.plan.provider_slug, []).append(match)

    def add_row(provider_slug: str, price: Decimal | None, basis: str, *,
                plan_name: str = "", vcpu: int | None = None,
                ram_gb: Decimal | None = None, disk_gb: Decimal | None = None,
                rate_verification: str = "not_applicable", observed_at: str = "",
                offering_id: int | None = None, notes: list[str] | None = None,
                provenance: str = "live", source_document: str = "",
                valid_until: str = "", disk_type: str = ""):
        notes = list(notes or [])
        if offering_id:
            history = repo.offering_history(offering_id)
            if history:
                from normalization.persian import normalize_billing_period
                if normalize_billing_period(history[0]['billing_period_raw']) == 'hourly':
                    notes.append(f"معادل ماهانه استاندارد ({history[0]['conversion_hours'] or 'نامشخص'} ساعت)، نه بسته ماهانه منتشرشده")
        view["rows"].append(VmRow(
            provider_slug=provider_slug,
            provider_name=provider_names.get(provider_slug, provider_slug),
            plan_name=plan_name, vcpu=vcpu or 0, ram_gb=ram_gb or Decimal(0),
            disk_gb=disk_gb or Decimal(0), price_in_toman=price, basis=basis,
            rate_verification=rate_verification, observed_at=observed_at,
            offering_id=offering_id, notes=notes or [],
            provenance=provenance, source_document=source_document,
            valid_until=valid_until, disk_type=disk_type,
        ))

    for slug in sorted(set(collected_providers) | {p.slug for p in providers_file.providers}):
        # 1) Published bundle exactly matching the reference size (CPU/RAM/disk)
        if slug in primary_by_provider:
            for match in primary_by_provider[slug]:
                p = match.plan
                manual = p.provenance == "manual"
                notes = []
                if slug == "parspack" and parspack_facts is not None:
                    notes.append(_parspack_adjustment_note(parspack_facts))
                if manual:
                    notes.append(_manual_source_note(p.source_document, p.valid_until))
                    notes.append(_manual_calculation_note(
                        p.vcpu, p.disk_gb, p.provider_tier_raw, p.disk_type
                    ))
                add_row(
                    slug, p.price_in_toman, "calculated" if manual else "published",
                    plan_name=p.plan_name,
                    vcpu=p.vcpu, ram_gb=p.ram_gb, disk_gb=p.disk_gb,
                    observed_at=p.observed_at, offering_id=_offering_id(repo, slug, p),
                    notes=notes, provenance=p.provenance,
                    source_document=p.source_document, valid_until=p.valid_until,
                    disk_type=p.disk_type,
                )
            continue

        if slug not in collected_providers and slug not in rates_providers:
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
            notes = ["محاسبه‌شده از نرخ‌های اعلامی تأمین‌کننده (شامل IPv4)"]
            factor = rate_mappings[slug].calculated_price_factors.get(tier)
            if factor is not None and factor != Decimal("1"):
                notes.append("فرض: تخفیف ۳۰٪ خانواده‌ی بسته‌های اقتصادی بر نرخ‌های اعلامی اعمال شده است")
            add_row(
                slug, calculated_price, "calculated",
                plan_name=f"پیکربندی {SIZE_LABELS_FA[size_key]} {TIER_LABELS_FA[tier]}",
                vcpu=size.vcpu, ram_gb=Decimal(size.ram_gb), disk_gb=Decimal(size.disk_gb),
                observed_at=latest_observed_by_provider.get(slug, ""),
                notes=notes,
            )
            continue

        # 3) No rates available: exact-CPU/RAM near misses (disk differs), then
        #    nearest larger published bundles — both shown as تقریبی.
        near_miss = next((m for m in result.near_miss if m.plan.provider_slug == slug), None)
        approximate = next((m for m in result.approximate if m.plan.provider_slug == slug), None)
        match = near_miss or approximate
        if match is not None:
            p = match.plan
            notes = []
            if match.match_type == "approximate":
                notes.append("بسته‌ی بزرگ‌تر از مرجع؛ به‌عنوان تقریبی نمایش داده می‌شود")
            if slug == "parspack" and parspack_facts is not None:
                notes.append(_parspack_adjustment_note(parspack_facts))
            add_row(
                slug, p.price_in_toman, "approximate", plan_name=p.plan_name,
                vcpu=p.vcpu, ram_gb=p.ram_gb, disk_gb=p.disk_gb,
                observed_at=p.observed_at, offering_id=_offering_id(repo, slug, p),
                notes=notes, provenance=p.provenance,
                source_document=p.source_document, valid_until=p.valid_until,
                disk_type=p.disk_type,
            )
            continue

        # 4) Collected but nothing usable for this size
        add_row(slug, None, "missing", notes=["پلن منطبق یا قابل‌محاسبه برای این اندازه یافت نشد"])

    # Canonical provider order (providers.yaml declaration order) is the
    # primary sort key so every view lists providers identically.
    order = {"published": 0, "calculated": 1, "approximate": 2, "missing": 3}
    view["rows"].sort(key=lambda r: (
        provider_order.get(r.provider_slug, 99),
        order[r.basis],
        r.price_in_toman if r.price_in_toman is not None else Decimal("999999999999"),
    ))

    # Pure-CSS comparison bars (one per priced row, cheapest first; providers
    # without a usable price go last with an empty dashed track — never a
    # zero-width bar that could be read as a tiny price). Bar length is
    # proportional to the most expensive price in this same selection. With
    # no priced rows at all the chart is omitted: a set of empty dashed
    # placeholders carries no information the table doesn't already show.
    priced = [r for r in view["rows"] if r.price_in_toman is not None]
    if priced:
        max_price = max(r.price_in_toman for r in priced)
        chart = []
        for row in sorted(priced, key=lambda r: r.price_in_toman):
            chart.append({
                "provider_name": row.provider_name,
                "basis": row.basis,
                "plan_name": row.plan_name,
                "price": row.price_in_toman,
                "width_pct": max(int(row.price_in_toman / max_price * 100), 2),
            })
        for row in view["rows"]:
            if row.price_in_toman is None:
                chart.append({
                    "provider_name": row.provider_name,
                    "basis": "missing",
                    "plan_name": "",
                    "price": None,
                    "width_pct": 0,
                })
        view["chart"] = chart
    return view


def _parspack_adjustment_note(facts) -> str:
    """Owner-approved adjustments applied to ParsPack calculator quotes."""
    discount_percent = int(round((1 - facts.monthly_discount) * 100))
    ipv4 = format_toman(facts.ipv4_monthly_toman) if facts.ipv4_monthly_toman else None
    parts = []
    if ipv4:
        parts.append(f"شامل IPv4 ({ipv4} در ماه)")
    if discount_percent:
        parts.append(f"{discount_percent}٪ تخفیف خرید ماهانه")
    return "؛ ".join(parts) if parts else ""


