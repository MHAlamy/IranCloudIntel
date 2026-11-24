"""DBaaS comparison view assembly.

Two infrastructure classes share the same four reference sizes:
- local (Class A): premium/dedicated CPU with local storage;
- shared (Class B): shared CPU with network storage.

Rows are read from `price_observations` with `service_type='dbaas'`.
`product_family` stores both the class and the price basis, e.g.
`dbaas_local_calculated`, so the two classes never collapse into one series.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from config.loader import load_benchmarks, load_providers
from storage.repository import Repository
from util.format import format_number
from util.jalali import format_jalali

SIZE_LABELS_FA = {
    "small": "کوچک",
    "medium": "متوسط",
    "large": "بزرگ",
    "very_large": "خیلی بزرگ",
}

CLASS_NOTES = {
    "local": [
        "کلاس A — محلی/پرمیوم: پردازنده اختصاصی یا پرمیوم و ذخیره‌سازی محلی.",
        "هم‌روش: نرخ پلن مدیریت‌شده؛ صفحه فقط «SSD» اعلام کرده و محلی بودن دیسک تأیید نشده است.",
        "ستون: بسته محاسباتی اختصاصی C1 × تعداد واحد + دیسک محلی از سند قیمت.",
        "آروان: نرخ منابع پرمیوم + دیسک لوکال از جدول نرخ‌ها.",
    ],
    "shared": [
        "کلاس B — اشتراکی/شبکه: پردازنده اشتراکی و ذخیره‌سازی شبکه‌ای.",
        "ستون: بسته اشتراکی E1 × تعداد واحد + دیسک مانا نوع ۲ (پرمیوم) از سند قیمت.",
        "آروان: نرخ منابع استاندارد + دیسک SSD شبکه‌ای.",
        "لیارا: پلن‌های منتشرشده‌ی سطح نقره‌ای؛ نوع دیسک در صفحه فقط SSD اعلام شده است.",
    ],
}

PROVIDER_NOTES = {
    ("arvan", "local"): [
        "محاسبه از نرخ‌های PAYG پرمیوم + دیسک لوکال؛ ترافیک و بکاپ رایگان، IPv4 جداگانه",
    ],
    ("arvan", "shared"): [
        "محاسبه از نرخ‌های PAYG استاندارد + دیسک SSD شبکه‌ای؛ ترافیک و بکاپ رایگان، IPv4 جداگانه",
    ],
    ("hamravesh", "local"): [
        "نرخ پلن مدیریت‌شده؛ نود استندبای/رپلیکا و IPv4 در نرخ پایه مشخص نیستند",
    ],
    ("sotoon", "local"): [
        "بسته محاسباتی اختصاصی ۱ vCPU + ۲ GB × تعداد واحد + دیسک محلی؛ دیتاسنتر ندا",
    ],
    ("sotoon", "shared"): [
        "بسته محاسباتی اشتراکی ۱ vCPU + ۲ GB × تعداد واحد + دیسک مانا ۲ (پرمیوم)؛ دیتاسنتر ندا",
    ],
    ("liara", "shared"): ["پلن منتشرشده‌ی لیارا در سطح نقره‌ای"],
}

GENERAL_NOTES = [
    "همه قیمت‌ها ماهانه و به تومان هستند؛ مالیات، ترافیک و IPv4 لحاظ نشده‌اند.",
    "هزینه رپلیکا/نود استندبای در نرخ پایه مشخص نیست و لحاظ نشده؛ "
    "در صورت الزام، قیمت هر تأمین‌کننده بالاتر می‌رود.",
    "قیمت‌های محاسبه‌شده از نرخ‌های ماهانه‌ی منتشرشده‌ی همان صفحه به‌دست آمده‌اند؛ "
    "پیکربندی منتشرنشده با حدس ساخته نشده است.",
]


@dataclass
class DbaasRow:
    provider_slug: str
    provider_name: str
    plan_name: str
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    disk_type: str
    price_in_toman: Decimal | None
    basis: str  # published | calculated | approximate | missing
    provider_tier_raw: str
    observed_at: str
    offering_id: int | None
    notes: list[str] = field(default_factory=list)


def _basis_from_family(family: str) -> str:
    basis = (family or "").rsplit("_", 1)[-1]
    return basis if basis in {"published", "calculated"} else "calculated"


def _missing_notes(has_provider_rows: bool, has_class_rows: bool) -> list[str]:
    if not has_provider_rows:
        return ["هنوز گردآوری نشده"]
    if not has_class_rows:
        return ["برای این کلاس داده‌ای ثبت نشده است"]
    return ["پلن منطبق برای این ترکیب یافت نشد"]


def build_dbaas_view(
    repo: Repository, class_key: str | None = None, size_key: str | None = None,
) -> dict:
    benchmarks = load_benchmarks().dbaas
    if not benchmarks.classes or not benchmarks.sizes:
        raise ValueError("benchmarks.yaml defines no dbaas classes/sizes")
    if class_key not in benchmarks.classes:
        class_key = next(iter(benchmarks.classes))
    if size_key not in benchmarks.sizes:
        size_key = next(iter(benchmarks.sizes))
    selection = benchmarks.sizes[size_key]
    class_config = benchmarks.classes[class_key]

    providers_file = load_providers()
    provider_names = {p.slug: p.name for p in providers_file.providers}

    observations = repo.latest_observations(service_type="dbaas")
    by_provider: dict[str, list] = {}
    for row in observations:
        if row["billing_period"] != "monthly":
            continue
        by_provider.setdefault(row["provider_slug"], []).append(row)

    rows: list[DbaasRow] = []
    for slug in class_config.providers:
        provider_rows = by_provider.get(slug, [])
        family_prefix = f"dbaas_{class_key}_"
        class_rows = [
            row for row in provider_rows
            if (row["product_family"] or "").startswith(family_prefix)
        ]
        matching = [
            row for row in class_rows
            if int(row["vcpu"] or 0) == selection.vcpu
            and Decimal(str(row["ram_gb"] or 0)) == Decimal(selection.ram_gb)
        ]
        exact = [
            row for row in matching
            if Decimal(str(row["disk_gb"] or 0)) == Decimal(selection.disk_gb)
        ]
        chosen = (
            min(exact, key=lambda r: Decimal(r["price_in_toman"])) if exact
            else min(matching, key=lambda r: Decimal(r["price_in_toman"])) if matching
            else None
        )

        if chosen is None:
            rows.append(DbaasRow(
                provider_slug=slug,
                provider_name=provider_names.get(slug, slug),
                plan_name="", vcpu=selection.vcpu,
                ram_gb=Decimal(selection.ram_gb), disk_gb=Decimal(selection.disk_gb),
                disk_type="", price_in_toman=None, basis="missing",
                provider_tier_raw="", observed_at="", offering_id=None,
                notes=_missing_notes(bool(provider_rows), bool(class_rows)),
            ))
            continue

        disk = Decimal(str(chosen["disk_gb"] or 0))
        basis = _basis_from_family(chosen["product_family"])
        notes = list(PROVIDER_NOTES.get((slug, class_key), []))
        if disk != Decimal(selection.disk_gb):
            basis = "approximate"
            notes.append(
                f"دیسک واقعی {format_number(disk)} GB در برابر مرجع "
                f"{format_number(selection.disk_gb)} GB"
            )
        if chosen["collection_method"] == "manual":
            source_document = chosen["source_document"] or "سند قیمت دستی"
            valid = (
                f" · معتبر تا {format_jalali(chosen['valid_until'], with_time=False)}"
                if chosen["valid_until"] else ""
            )
            notes.append(f"منبع دستی: {source_document}{valid}")

        rows.append(DbaasRow(
            provider_slug=slug,
            provider_name=provider_names.get(slug, slug),
            plan_name=chosen["plan_name"],
            vcpu=int(chosen["vcpu"] or 0),
            ram_gb=Decimal(str(chosen["ram_gb"] or 0)),
            disk_gb=disk,
            disk_type=chosen["disk_type"] or "",
            price_in_toman=Decimal(chosen["price_in_toman"]),
            basis=basis,
            provider_tier_raw=chosen["provider_tier_raw"] or "",
            observed_at=chosen["observed_at"],
            offering_id=chosen["offering_id"],
            notes=notes,
        ))

    priced = [r for r in rows if r.price_in_toman is not None]
    chart: list[dict] = []
    if priced:
        max_price = max(r.price_in_toman for r in priced)
        for row in sorted(priced, key=lambda r: r.price_in_toman):
            chart.append({
                "provider_name": row.provider_name,
                "basis": row.basis,
                "plan_name": row.plan_name,
                "price": row.price_in_toman,
                "width_pct": max(int(row.price_in_toman / max_price * 100), 2),
            })
        for row in rows:
            if row.price_in_toman is None:
                chart.append({
                    "provider_name": row.provider_name,
                    "basis": "missing", "plan_name": "", "price": None, "width_pct": 0,
                })

    return {
        "class": class_key,
        "class_label": class_config.label,
        "class_notes": CLASS_NOTES.get(class_key, []),
        "classes": [
            {"key": key, "label": value.label}
            for key, value in benchmarks.classes.items()
        ],
        "size": size_key,
        "sizes": [
            {
                "key": key,
                "label": SIZE_LABELS_FA.get(key, key),
                "vcpu": value.vcpu,
                "ram_gb": value.ram_gb,
                "disk_gb": value.disk_gb,
            }
            for key, value in benchmarks.sizes.items()
        ],
        "target": {
            "vcpu": selection.vcpu,
            "ram_gb": selection.ram_gb,
            "disk_gb": selection.disk_gb,
        },
        "rows": rows,
        "chart": chart,
        "notes": GENERAL_NOTES,
    }
