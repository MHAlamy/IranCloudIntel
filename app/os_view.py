"""Object Storage comparison view assembly."""
from decimal import Decimal
from config.loader import load_benchmarks, load_providers
from storage.repository import Repository
from util.format import format_number, format_toman
from app.view_common import _provider_id
from comparison.tariffs import tier_cost as _tier_cost

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


def build_os_view(repo: Repository, scenario_key: str | None = None) -> dict:
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
        return {"price": price, "basis": basis, "plan_name": plan_name, "notes": notes + ["جمع جزئی؛ هزینه درخواست‌ها و مالیات لحاظ نشده است"]}

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

    selected = next((s for s in scenarios if s['key'] == scenario_key), scenarios[0] if scenarios else None)
    comparison_rows = []
    if selected:
        for slug in os_provider_slugs:
            comparison_rows.append(dict(selected['providers'][slug], provider_name=provider_names.get(slug, slug)))
    priced = sorted((r for r in comparison_rows if r['price'] is not None), key=lambda r: r['price'])
    missing = [r for r in comparison_rows if r['price'] is None]
    maximum = max((r['price'] for r in priced), default=Decimal(0))
    chart = [dict(r, width_pct=max(int(r['price'] / maximum * 100), 2) if maximum else 0) for r in priced]
    if priced:
        chart.extend(dict(r, width_pct=0) for r in missing)

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
        "selected_scenario": selected,
        "comparison_rows": comparison_rows,
        "chart": chart,
        "provider_sections": provider_sections,
        "rate_sections": rate_sections,
        "baseline_name": provider_names.get(baseline_slug, baseline_slug),
    }


