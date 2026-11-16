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
from config.loader import load_analyst_facts  # noqa: E402
from config.loader import load_benchmarks, load_providers, load_tiers  # noqa: E402
from util.format import format_number, format_toman  # noqa: E402
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
            "SELECT DISTINCT p.slug AS slug FROM resource_rates r JOIN providers p ON p.id = r.provider_id"
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
           FROM resource_rates r JOIN providers p ON p.id = r.provider_id
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
                offering_id: int | None = None, notes: list[str] | None = None):
        view["rows"].append(VmRow(
            provider_slug=provider_slug,
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
                notes = []
                if slug == "parspack" and parspack_facts is not None:
                    notes.append(_parspack_adjustment_note(parspack_facts))
                add_row(
                    slug, p.price_in_toman, "published", plan_name=p.plan_name,
                    vcpu=p.vcpu, ram_gb=p.ram_gb, disk_gb=p.disk_gb,
                    observed_at=p.observed_at, offering_id=_offering_id(repo, slug, p),
                    notes=notes,
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
                notes=notes,
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


# -- Object Storage view (price_gathering_guide.md 7) -------------------------

OS_BASIS_LABELS_FA = {
    "published": "منتشرشده",
    "calculated": "محاسبه‌شده",
    "approximate": "تقریبی",
    "missing": "در دسترس نیست",
}
OS_STATUS_LABELS_FA = {
    "priced": "پلن قیمت‌دار",
    "free": "رایگان",
    "quote_only": "با استعلام قیمت",
}

# storage/traffic rate categories and their dashboard grouping
_OS_RATE_GROUPS = [
    ("storage", "فضای ذخیره‌سازی"),
    ("traffic", "ترافیک"),
    ("requests_read", "درخواست خواندن"),
    ("requests_write", "درخواست نوشتن"),
    ("feature", "قابلیت‌ها"),
]


def _tier_cost(rates: list[dict], quantity_gb: Decimal) -> tuple[Decimal | None, bool]:
    """Cost of `quantity_gb` under tiered (min_gb, max_gb, amount, is_free) rows.

    Returns (total | None, fully_covered). Tiers are consumed in ascending
    order; unbounded last tiers (max=None) absorb the remainder. None means
    the quantity exceeds every documented bounded tier without an unbounded one.
    """
    ordered = sorted(
        (r for r in rates if not r["is_free"] and r["amount"] is not None),
        key=lambda r: Decimal(r["range_min_gb"] or "0"),
    )
    free_rows = [r for r in rates if r["is_free"]]
    remaining = quantity_gb
    total = Decimal("0")

    # consume documented free allowances first
    for row in free_rows:
        lo = Decimal(row["range_min_gb"] or "0")
        hi = Decimal(row["range_max_gb"]) if row["range_max_gb"] is not None else None
        span = (hi - lo) if hi is not None else remaining
        take = min(remaining, span) if remaining > 0 else Decimal("0")
        remaining -= take

    for row in ordered:
        if remaining <= 0:
            break
        lo = Decimal(row["range_min_gb"] or "0")
        hi = Decimal(row["range_max_gb"]) if row["range_max_gb"] is not None else None
        span = (hi - lo) if hi is not None else remaining
        if span <= 0:
            continue
        take = min(remaining, span)
        total += take * Decimal(row["amount"])
        remaining -= take
    return (total, remaining <= 0)


# Per-provider scenario resolution for rates-based providers: which rate rows
# count as storage and as the "traffic" component of a scenario.
# - arvan: standard storage tiers; traffic = download tiers
# - kubit: all storage tiers; traffic = egress to outside the location
#   (خروجی خارج موقعیت) — the closest analog of Hamravesh's unspecified
#   «ترافیک», chosen explicitly and labeled, not silently assumed.
OS_RATE_FILTERS = {
    "arvan": {
        "storage": lambda r: "استاندارد" in (r["tier_label"] or ""),
        "traffic": lambda r: "دانلود" in (r["tier_label"] or ""),
    },
    "kubit": {
        "storage": lambda r: True,
        "traffic": lambda r: "خروجی" in (r["tier_label"] or "") and "خارج" in (r["tier_label"] or ""),
    },
}

# Provider-level caveats shown with plan tables and scenario cells.
OS_PROVIDER_NOTES = {
    "arvan": [
        "فرض: نرخ‌های مصرف مازاد ماهانه‌اند — دوره‌ی صورتحساب در جدول نرخ صفحه صریح نشده است",
        "هزینه‌ی درخواست‌ها مستثنی است: هم‌روش سهمیه‌ی درخواست منتشر نمی‌کند",
    ],
    "parspack": [
        "ترافیک در تعرفه لحاظ نشده است (ماشین‌حساب فقط حجم ذخیره‌سازی را قیمت‌گذاری می‌کند)",
    ],
    "kubit": [
        "ترافیک سناریو: خروجی به خارج از موقعیت؛ ورودی، خروجی داخلی و درخواست‌ها لحاظ نشده‌اند",
        "۱۰٪ مالیات بر ارزش افزوده به تعرفه‌ها اضافه می‌شود (طبق صفحه کوبیت)",
        "پلن پایه رایگان با سهمیه صفر است؛ کل مصرف طبق تعرفه‌های مصرف مازاد محاسبه می‌شود",
    ],
}


def _rates_scenario_price(
    rates: list[dict], storage_gb: Decimal, traffic_gb: Decimal, filters: dict,
) -> tuple[Decimal | None, list[str]]:
    """Calculated scenario price from a provider's documented PAYG rates.

    Request charges stay excluded for every provider: the Hamravesh baseline
    publishes no request allowance, so including them would compare unlike
    assumptions (unknown ≠ zero).
    """
    storage_rows = [
        {"range_min_gb": r["range_min_gb"], "range_max_gb": r["range_max_gb"],
         "amount": r["amount_toman"], "is_free": bool(r["is_free"])}
        for r in rates if r["category"] == "storage" and filters["storage"](r)
    ]
    traffic_rows = [
        {"range_min_gb": r["range_min_gb"], "range_max_gb": r["range_max_gb"],
         "amount": r["amount_toman"], "is_free": bool(r["is_free"])}
        for r in rates if r["category"] == "traffic" and filters["traffic"](r)
    ]
    storage_cost, storage_ok = _tier_cost(storage_rows, storage_gb)
    traffic_cost, traffic_ok = _tier_cost(traffic_rows, traffic_gb)
    if storage_cost is None or not storage_ok:
        return None, ["حجم ذخیره‌سازی سناریو فراتر از پلکان‌های نرخ منتشرشده است"]
    if traffic_cost is None or not traffic_ok:
        return None, ["حجم ترافیک سناریو فراتر از پلکان‌های نرخ منتشرشده است"]
    notes: list[str] = []
    if storage_rows and traffic_rows:
        notes.append("محاسبه از نرخ‌های مصرف مازاد (PAYG) منتشرشده؛ شامل سهمیه‌های رایگان مستندشده")
    return storage_cost + traffic_cost, notes


def _format_gb(value) -> str:
    if value is None:
        return "—"
    gb = Decimal(str(value))
    if gb >= 1024 and gb % 1024 == 0:
        return f"{format_number(gb / 1024)} ترابایت"
    return f"{format_number(gb)} گیگابایت"


def _format_compact(gb: Decimal, tb_to_gb: int) -> str:
    """Compact capacity label, e.g. Decimal(2048) -> '۲GB' ... '۵TB'."""
    gb = Decimal(gb)
    if gb >= tb_to_gb and gb % tb_to_gb == 0:
        return f"{format_number(gb / tb_to_gb)}TB"
    return f"{format_number(gb)}GB"


def build_os_view(repo: Repository) -> dict:
    benchmarks = load_benchmarks().object_storage
    providers_file = load_providers()
    provider_names = {p.slug: p.name for p in providers_file.providers}
    provider_order = {p.slug: i for i, p in enumerate(providers_file.providers)}
    baseline_slug = benchmarks.baseline

    # Providers with an object-storage source, in providers.yaml declaration
    # order — the canonical column/legend order for the OS dashboard.
    os_provider_slugs = [
        p.slug for p in providers_file.providers
        if any(s.service_type == "object_storage" for s in p.sources)
    ]

    plans_by_provider: dict[str, list] = {}
    for row in repo.latest_os_observations():
        plans_by_provider.setdefault(row["provider_slug"], []).append(row)

    rates_by_provider: dict[str, list] = {}
    for slug in os_provider_slugs:
        pid = _provider_id(repo, slug)
        if pid:
            rates = repo.latest_os_rates(pid)
            if rates:
                rates_by_provider[slug] = rates

    arvan_rates = rates_by_provider.get("arvan", [])

    review_flags: list[str] = []
    # deterministic divergence check: FAQ overage figures vs the rate table
    faq = {r["tier_label"]: Decimal(r["amount_toman"]) for r in arvan_rates if r["category"] == "faq_overage"}
    table_storage = [
        Decimal(r["amount_toman"]) for r in arvan_rates
        if r["category"] == "storage" and "استاندارد" in r["tier_label"]
        and not r["is_free"] and r["amount_toman"]
    ]
    table_traffic = [
        Decimal(r["amount_toman"]) for r in arvan_rates
        if r["category"] == "traffic" and not r["is_free"] and r["amount_toman"]
    ]
    if faq.get("فضای ذخیره‌سازی") and table_storage and faq["فضای ذخیره‌سازی"] != min(table_storage):
        review_flags.append(
            f"نرخ مصرف مازاد ذخیره‌سازی در پرسش‌های رایج ({format_toman(faq['فضای ذخیره‌سازی'], False)}) "
            f"با جدول نرخ‌ها ({format_toman(min(table_storage), False)}) ناهمخوان است — نیازمند بررسی"
        )
    if faq.get("ترافیک") and table_traffic and faq["ترافیک"] != min(table_traffic):
        review_flags.append(
            f"نرخ مصرف مازاد ترافیک در پرسش‌های رایج ({format_toman(faq['ترافیک'], False)}) "
            f"با جدول نرخ‌ها ({format_toman(min(table_traffic), False)}) ناهمخوان است — نیازمند بررسی"
        )

    def plan_public_row(row) -> dict:
        return {
            "plan_name": row["plan_name"],
            "status": row["plan_status"],
            "status_fa": OS_STATUS_LABELS_FA[row["plan_status"]],
            "price": Decimal(row["price_in_toman"]) if row["price_in_toman"] is not None else None,
            "storage_fa": "نامحدود" if row["storage_unlimited"] else _format_gb(row["storage_included_gb"]),
            "traffic_fa": "نامحدود" if row["traffic_unlimited"] else _format_gb(row["traffic_included_gb"]),
            "requests_fa": (
                "نامحدود" if row["requests_unlimited"]
                else format_number(row["requests_included"]) if row["requests_included"] is not None else "—"
            ),
            "overage_storage": (
                format_toman(Decimal(row["overage_storage_toman_gb"]), False)
                if row["overage_storage_toman_gb"] else "—"
            ),
            "overage_traffic": (
                format_toman(Decimal(row["overage_traffic_toman_gb"]), False)
                if row["overage_traffic_toman_gb"] else "—"
            ),
            "offering_id": row["offering_id"],
            "observed_at": row["observed_at"],
        }

    provider_sections = []
    for slug in sorted(plans_by_provider, key=lambda s: provider_order.get(s, 99)):
        rows = sorted(plans_by_provider[slug], key=lambda r: r["plan_name"])
        provider_sections.append({
            "slug": slug,
            "name": provider_names.get(slug, slug),
            "notes": OS_PROVIDER_NOTES.get(slug, []),
            "plans": [plan_public_row(r) for r in rows],
        })

    baseline_plans = plans_by_provider.get(baseline_slug, [])

    def _plan_storage(row) -> Decimal | None:
        return Decimal(str(row["storage_included_gb"])) if row["storage_included_gb"] is not None else None

    def _plan_traffic(row) -> Decimal | None:
        return Decimal(str(row["traffic_included_gb"])) if row["traffic_included_gb"] is not None else None

    def find_plan(plans, storage_gb: Decimal, traffic_gb: Decimal):
        for row in plans:
            if _plan_storage(row) == storage_gb and _plan_traffic(row) == traffic_gb:
                return row
        return None

    def _cell(price, basis: str, plan_name: str, notes: list[str]) -> dict:
        return {"price": price, "basis": basis, "plan_name": plan_name, "notes": notes}

    def resolve_cell(slug: str, storage_gb: Decimal, traffic_gb: Decimal) -> dict:
        """One provider's comparable price at one baseline consumption point.

        Precedence for every provider: an exactly matching published bundle
        (storage AND traffic) is a real purchasable price and wins; otherwise
        a rates-based provider is calculated from documented PAYG rates;
        storage-only quote providers (e.g. ParsPack) use their exact storage
        quote with the no-traffic caveat, then the nearest larger quote marked
        approximate with its actual capacity.
        """
        plans = plans_by_provider.get(slug, [])
        rates = rates_by_provider.get(slug)
        provider_notes = list(OS_PROVIDER_NOTES.get(slug, []))

        if slug == baseline_slug:
            row = find_plan(plans, storage_gb, traffic_gb)
            if row is None:
                return _cell(None, "missing", "", [])
            price = Decimal(row["price_in_toman"]) if row["price_in_toman"] is not None else None
            return _cell(price, "published", row["plan_name"], [])

        exact = [p for p in plans if _plan_storage(p) == storage_gb and _plan_traffic(p) == traffic_gb]
        if exact:
            row = min(exact, key=lambda r: Decimal(r["price_in_toman"]))
            price = Decimal(row["price_in_toman"]) if row["price_in_toman"] is not None else None
            return _cell(price, "published", row["plan_name"], provider_notes)

        if rates is not None:
            filters = OS_RATE_FILTERS.get(slug)
            price, notes = _rates_scenario_price(rates, storage_gb, traffic_gb, filters) if filters else (None, [])
            if price is None:
                return _cell(None, "missing", "", notes + provider_notes)
            return _cell(price, "calculated", "پیکربندی معادل", notes + provider_notes)

        storage_only = [
            p for p in plans
            if _plan_storage(p) == storage_gb
            and p["traffic_included_gb"] is None and not p["traffic_unlimited"]
        ]
        if storage_only:
            row = min(storage_only, key=lambda r: Decimal(r["price_in_toman"]))
            price = Decimal(row["price_in_toman"]) if row["price_in_toman"] is not None else None
            return _cell(price, "published", row["plan_name"], provider_notes)

        larger = [p for p in plans if _plan_storage(p) is not None and _plan_storage(p) > storage_gb]
        if larger:
            nearest = min(larger, key=lambda r: Decimal(r["storage_included_gb"]))
            actual = Decimal(str(nearest["storage_included_gb"]))
            factor = (actual / storage_gb).quantize(Decimal("0.1"))
            note = (
                f"نزدیک‌ترین تعرفه بزرگ‌تر: {_format_compact(actual, benchmarks.tb_to_gb)} "
                f"(حدود {format_number(factor)} برابر حجم درخواستی)"
            )
            price = Decimal(nearest["price_in_toman"]) if nearest["price_in_toman"] is not None else None
            return _cell(price, "approximate", nearest["plan_name"], [note] + provider_notes)

        return _cell(None, "missing", "", provider_notes)

    scenarios = []
    for key, scenario in benchmarks.scenarios.items():
        storage_gb = Decimal(str(scenario.storage_gb))
        traffic_gb = Decimal(str(scenario.traffic_gb))
        scenarios.append({
            "key": key,
            "label": scenario.label,
            "label_compact": (
                f"{_format_compact(storage_gb, benchmarks.tb_to_gb)}/"
                f"{_format_compact(traffic_gb, benchmarks.tb_to_gb)}"
            ),
            "storage_fa": _format_gb(storage_gb),
            "traffic_fa": _format_gb(traffic_gb),
            "providers": {
                slug: resolve_cell(slug, storage_gb, traffic_gb)
                for slug in os_provider_slugs
            },
        })

    # One grouped bar chart. Bars are scaled within each scenario (the
    # priciest option of that point = full track): the chart's job is showing
    # how much cheaper each option is at each consumption point, and log or
    # global-linear scaling both distort that perception (log compresses
    # ratios; a global linear axis hides the small plans entirely).
    chart_groups = []
    for scenario in scenarios:
        prices = [scenario["providers"][slug]["price"] for slug in os_provider_slugs]
        group_max = max((p for p in prices if p is not None), default=None)
        bars = []
        for slug in os_provider_slugs:
            cell = scenario["providers"][slug]
            badge_key = cell["basis"] if cell["basis"] not in (None, "published", "missing") else None
            bars.append({
                "cls": f"os-{slug}",
                "price": cell["price"],
                "basis": cell["basis"],
                "width_pct": (
                    max(int(cell["price"] / group_max * 100), 2)
                    if cell["price"] is not None and group_max else 0
                ),
                "badge": OS_BASIS_LABELS_FA.get(badge_key) if badge_key else None,
            })
        chart_groups.append({"label": scenario["label"], "compact": scenario["label_compact"], "bars": bars})
    chart = {
        "legend": [{"cls": f"os-{slug}", "name": provider_names.get(slug, slug)} for slug in os_provider_slugs],
        "groups": chart_groups,
    }

    # PAYG rate tables per provider (collapsible on the page)
    rate_sections = []
    for slug in os_provider_slugs:
        rates = rates_by_provider.get(slug)
        if not rates:
            continue
        tables = []
        for category, title in _OS_RATE_GROUPS:
            rows = [
                {
                    "tier": r["tier_label"] or "—",
                    "range": r["range_label"] or "—",
                    "unit": r["unit"],
                    "amount": (
                        "رایگان" if r["is_free"]
                        else format_toman(Decimal(r["amount_toman"]), False) if r["amount_toman"] else "—"
                    ),
                }
                for r in rates if r["category"] == category
            ]
            if rows:
                tables.append({"title": title, "rows": rows})
        if tables:
            rate_sections.append({"provider_name": provider_names.get(slug, slug), "tables": tables})

    return {
        "os_providers": [
            {"slug": slug, "name": provider_names.get(slug, slug), "is_baseline": slug == baseline_slug}
            for slug in os_provider_slugs
        ],
        "baseline_slug": baseline_slug,
        "scenarios": scenarios,
        "chart": chart,
        "provider_sections": provider_sections,
        "rate_sections": rate_sections,
        "review_flags": review_flags,
        "baseline_name": provider_names.get(baseline_slug, baseline_slug),
    }


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


def build_status_view(repo: Repository) -> dict:
    # same canonical provider order as the comparison views
    provider_order = {p.slug: i for i, p in enumerate(load_providers().providers)}
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
    sources.sort(key=lambda s: provider_order.get(s["provider_slug"], 99))
    return {"sources": sources}
