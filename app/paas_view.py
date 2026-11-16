"""PaaS/CNAP comparison view assembly.

Four fixed compute references, one provider row per provider, the shared
price chart and a provider-row table. Liara is compared on its silver tier;
Hamravesh and Arvan are calculated from their published monthly resource rates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from config.loader import load_benchmarks, load_providers
from storage.repository import Repository
from util.format import format_number

PROVIDER_NOTES = {
    "arvan": "محاسبه‌شده از نرخ‌های PAYG رسمی؛ بدون ترافیک، IPv4، بکاپ و اسنپ‌شات",
    "hamravesh": "محاسبه‌شده از نرخ‌های دیتاسنتر ایران؛ بدون ترافیک، IPv4 و مانیتورینگ",
    "liara": "پلن منتشرشده‌ی لیارا",
}

SMALL_NOTE = (
    "ماشین‌حساب عمومی آروان ترکیب ۱ vCPU + ۲ GB را قابل انتخاب نمی‌کند؛ "
    "قیمت از نرخ‌های PAYG محاسبه شده است"
)
LARGE_DISK_NOTE = (
    "حجم SSD از سقف اسلایدر ماشین‌حساب آروان (۲۰۰ GB) بیشتر است؛ "
    "قیمت از نرخ‌های PAYG محاسبه شده است"
)


@dataclass
class PaasRow:
    provider_slug: str
    provider_name: str
    plan_name: str
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    price_in_toman: Decimal | None
    basis: str
    provider_tier_raw: str
    observed_at: str
    offering_id: int | None
    notes: list[str] = field(default_factory=list)


def _row_basis(row) -> str:
    if row["product_family"] == "paas_fixed":
        return "published"
    return "calculated"


def _selection_notes(slug: str, key: str) -> list[str]:
    notes = [PROVIDER_NOTES[slug]] if slug in PROVIDER_NOTES else []
    if slug == "arvan" and key == "s1":
        notes.append(SMALL_NOTE)
    if slug == "arvan" and key in ("s3", "s4"):
        notes.append(LARGE_DISK_NOTE)
    return notes


def build_paas_view(repo: Repository, selection_key: str | None = None) -> dict:
    benchmarks = load_benchmarks().paas
    selections = benchmarks.selections
    if not selections:
        raise ValueError("benchmarks.yaml defines no paas.selections")
    if selection_key not in selections:
        selection_key = next(iter(selections))
    selection = selections[selection_key]

    providers_file = load_providers()
    provider_names = {p.slug: p.name for p in providers_file.providers}
    provider_order = {p.slug: i for i, p in enumerate(providers_file.providers)}
    paas_providers = [
        p.slug for p in providers_file.providers
        if any(s.service_type == "paas" for s in p.sources)
    ]

    plans_by_provider: dict[str, list] = {}
    for row in repo.latest_observations(service_type="paas"):
        if row["billing_period"] != "monthly":
            continue
        plans_by_provider.setdefault(row["provider_slug"], []).append(row)

    rows: list[PaasRow] = []
    for slug in paas_providers:
        provider_rows = plans_by_provider.get(slug, [])
        matching = [
            row for row in provider_rows
            if int(row["vcpu"] or 0) == selection.vcpu
            and Decimal(str(row["ram_gb"] or 0)) == Decimal(selection.ram_gb)
        ]
        exact = [
            row for row in matching
            if Decimal(str(row["disk_gb"] or 0)) == Decimal(selection.disk_gb)
        ]
        chosen = min(exact, key=lambda r: Decimal(r["price_in_toman"])) if exact else (
            min(matching, key=lambda r: Decimal(r["price_in_toman"])) if matching else None
        )

        if chosen is None:
            if not provider_rows:
                notes = ["هنوز گردآوری نشده"]
            elif slug == "liara" and selection_key == "s4":
                notes = ["لیارا در سطح نقره‌ای پلن ۳۲ vCPU + ۶۴ GB RAM ندارد"]
            else:
                notes = ["پلن منطبق برای این ترکیب یافت نشد"]
            rows.append(PaasRow(
                provider_slug=slug,
                provider_name=provider_names.get(slug, slug),
                plan_name="", vcpu=selection.vcpu,
                ram_gb=Decimal(selection.ram_gb), disk_gb=Decimal(selection.disk_gb),
                price_in_toman=None, basis="missing",
                provider_tier_raw="", observed_at="", offering_id=None, notes=notes,
            ))
            continue

        disk = Decimal(str(chosen["disk_gb"] or 0))
        tier_raw = chosen["provider_tier_raw"] or ""
        notes = _selection_notes(slug, selection_key)
        if disk != Decimal(selection.disk_gb):
            basis = "approximate"
            notes.append(
                f"دیسک واقعی {format_number(disk)} GB در برابر مرجع "
                f"{format_number(selection.disk_gb)} GB"
            )
        else:
            basis = _row_basis(chosen)
        rows.append(PaasRow(
            provider_slug=slug,
            provider_name=provider_names.get(slug, slug),
            plan_name=chosen["plan_name"],
            vcpu=int(chosen["vcpu"] or 0),
            ram_gb=Decimal(str(chosen["ram_gb"] or 0)),
            disk_gb=disk,
            price_in_toman=Decimal(chosen["price_in_toman"]),
            basis=basis,
            provider_tier_raw=tier_raw,
            observed_at=chosen["observed_at"],
            offering_id=chosen["offering_id"],
            notes=notes,
        ))

    basis_order = {"published": 0, "calculated": 1, "approximate": 2, "missing": 3}
    rows.sort(key=lambda r: (
        provider_order.get(r.provider_slug, 99),
        basis_order[r.basis],
        r.price_in_toman if r.price_in_toman is not None else Decimal("999999999999"),
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
        "selection": selection_key,
        "selection_label": f"{selection.vcpu} vCPU + {selection.ram_gb} GB",
        "selections": [
            {
                "key": key,
                "label": f"{value.vcpu} vCPU + {value.ram_gb} GB",
                "vcpu": value.vcpu,
                "ram_gb": value.ram_gb,
                "disk_gb": value.disk_gb,
            }
            for key, value in selections.items()
        ],
        "target": {
            "vcpu": selection.vcpu,
            "ram_gb": selection.ram_gb,
            "disk_gb": selection.disk_gb,
        },
        "rows": rows,
        "chart": chart,
        "liara_tier": benchmarks.liara_tier,
        "notes": [
            "قیمت‌ها ماهانه و به تومان هستند؛ مالیات و هزینه‌های ترافیک/IP لحاظ نشده‌اند.",
            "لیارا فقط در سطح نقره‌ای (Silver) مقایسه می‌شود.",
            "قیمت هم‌روش و آروان از نرخ‌های منتشرشده محاسبه شده است؛ "
            "ماشین‌حساب عمومی آروان بعضی ترکیب‌ها را قابل انتخاب نمی‌کند.",
        ],
    }
