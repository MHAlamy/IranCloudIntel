"""Managed Kubernetes (KaaS) comparison view assembly.

Four offerings are compared over six node-count scenarios: Hamravesh v1
(legacy fee schedule), Hamravesh v2 (current self-service KaaS), Kubit and
Sotoon. Component tariffs come from `resource_rates`; configured management
fees live in `benchmarks.yaml`, and all arithmetic is in
`comparison.kaas_pricing`. This module only loads rows and shapes them for the
shared chart and table templates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.view_common import _provider_id
from comparison.kaas_pricing import (
    FeeTier,
    KaasCost,
    KaasTariffs,
    hamravesh_cost,
    kubit_cost,
    parse_fee_tier_label,
    sotoon_cost,
)
from config.loader import load_benchmarks
from storage.repository import Repository
from util.jalali import format_jalali

PROVIDER_NOTE_1 = (
    "هم‌روش v1: قیمت‌های قدیمی؛ هزینه مدیریت ثابت ۷۰/۱۴۰/۲۲۰/۳۲۰ میلیون تومان "
    "(بر اساس مجموع vCPU کارگر) + منابع کارگر (vCPU، RAM و SSD محلی) + ۲۵ میلیون کنترل پلین."
)
PROVIDER_NOTE_2 = (
    "هم‌روش v2: قیمت‌های جدید نسخه‌ی خودسرویس KaaS؛ هزینه مدیریت ۳۰/۸۰/۱۵۰/۲۴۰ "
    "میلیون تومان (۲۴۰ برای پلکان «ثبت درخواست» فرض شده) + همان منابع کارگر + "
    "همان ۲۵ میلیون کنترل پلین."
)
PROVIDER_NOTE_KUBIT = (
    "کوبیت: لایسنس کوبرنتیز از پلکان P = ۲×CPU + RAM (منابع کارگر) + منابع کارگر "
    "با نرخ نسل ۴ (استاندارد) + ۱۰ میلیون تومان کنترل پلین."
)
PROVIDER_NOTE_SOTOON = (
    "ستون: بسته C1 دیتاسنتر ندا × کل vCPU کارگر + دیسک محلی + مدیریت کلاستر "
    "شامل اشتراک استاندارد/پریمیوم و هزینه هر نود (۳.۱/۳.۹ میلیون تومان)؛ "
    "کنترل پلین در اشتراک لحاظ شده است."
)
GENERAL_NOTES = [
    "همه مبالغ ماهانه و به تومان هستند؛ ماه ۷۲۰ ساعته، ۲ گیگابایت رم و "
    "۱۰ گیگابایت SSD محلی به ازای هر vCPU فرض شده است.",
    "مالیات، ترافیک، IPv4، پشتیبانی و افزونه‌های اختیاری لحاظ نشده‌اند.",
    "پلکان مدیریت v1 قیمت‌های قدیمی و پلکان v2 قیمت‌های جدید خودسرویس KaaS است؛ "
    "مبلغ ۲۴۰ میلیون برای پلکان «ثبت درخواست» v2 فرض شده و در صفحه منتشر نشده است. "
    "مبالغ کنترل پلین هم‌روش و کوبیت قواعد مقایسه‌ای مالک پروژه‌اند، نه نرخ استخراج‌شده.",
    "ستون قیمت‌ها را به ریال منتشر می‌کند؛ تبدیل با تقسیم بر ۱۰ انجام شده است. "
    "نرخ دیسک محلی ستون به اولترا ۳ نزدیک است و تقریب معتبری برای هر دو گزینه است.",
    "مقیاس‌دهی خطی C1 ستون یک فرض مقایسه‌ای است، نه پیکربندی نود تأییدشده.",
    "هزینه مدیریت ستون = اشتراک استاندارد/پریمیوم + تعداد نود × هزینه هر نود؛ "
    "هزینه هر نود در محاسبه لحاظ شده است. هسته‌های اضافی کنترل پلین ستون "
    "(اختیاری/پشتیبانی) و پلکان‌های «ثبت درخواست» یا «تماس بگیرید» به‌عنوان عدد ثبت نشده‌اند.",
]
ROW_NOTE_V1 = "قیمت‌های قدیمی KaaS؛ مدیریت ثابت ۷۰/۱۴۰/۲۲۰/۳۲۰ میلیون تومان"
ROW_NOTE_V2 = "قیمت‌های جدید خودسرویس KaaS؛ ۲۴۰ میلیون برای بازه‌ی «ثبت درخواست» فرض شده است"


@dataclass(frozen=True)
class Offering:
    key: str
    name: str
    provider_slug: str
    basis: str  # calculated
    fee_mode: str  # config_ladder | kubit_ladder | sotoon_nodes
    cpu_tier: str
    ram_tier: str | None
    storage_tier: str


OFFERINGS = (
    Offering("hamravesh_v1", "هم‌روش v1", "hamravesh", "calculated",
             "config_ladder", "kaas", "kaas", "kaas"),
    Offering("hamravesh_v2", "هم‌روش v2", "hamravesh", "calculated",
             "config_ladder", "kaas", "kaas", "kaas"),
    Offering("kubit", "Kubit", "kubit", "calculated",
             "kubit_ladder", "gen-4", "gen-4", ""),
    Offering("sotoon", "Sotoon", "sotoon", "calculated",
             "sotoon_nodes", "C1", None, "local_disk"),
)


@dataclass
class KaasRow:
    key: str
    provider_name: str
    basis: str
    nodes: int
    vcpu: int
    ram_gb: Decimal
    disk_gb: Decimal
    management_toman: Decimal | None
    worker_toman: Decimal | None
    control_plane_toman: Decimal | None
    total_toman: Decimal | None
    fee_label: str
    notes: list[str] = field(default_factory=list)
    observed_at: str = ""
    provenance: str = "live"


def _rates_for(repo: Repository, slug: str) -> tuple[list, str]:
    provider_id = _provider_id(repo, slug)
    if provider_id is None:
        return [], ""
    rows = repo.latest_rates(provider_id, region="iran")
    observed = max((row["observed_at"] for row in rows), default="")
    return rows, observed


def _tariffs(rows: list, offering: Offering, benchmarks) -> KaasTariffs | None:
    by_key = {(row["category"], row["tier_label"]): row for row in rows}

    def amount(category: str, tier: str | None) -> Decimal | None:
        if tier is None:
            return Decimal(0)
        row = by_key.get((category, tier))
        return Decimal(row["amount_toman"]) if row else None

    cpu = amount("cpu", offering.cpu_tier)
    ram = amount("ram", offering.ram_tier)
    storage = amount("storage", offering.storage_tier)
    if cpu is None or ram is None or storage is None:
        return None

    tiers: list[FeeTier] = []
    standard = premium = None
    standard_node = premium_node = None
    if offering.fee_mode == "config_ladder":
        configured = benchmarks.management_fees.get(offering.key, [])
        for index, fee in enumerate(configured):
            upper = configured[index + 1].min_vcpu if index + 1 < len(configured) else None
            tiers.append(FeeTier(fee.min_vcpu, upper, fee.fee_toman))
    elif offering.fee_mode == "kubit_ladder":
        for row in rows:
            if row["category"] != "management_fee":
                continue
            parsed = parse_fee_tier_label(row["tier_label"])
            if parsed:
                tiers.append(FeeTier(parsed[0], parsed[1], Decimal(row["amount_toman"])))
    else:  # sotoon_nodes
        for row in rows:
            if row["category"] != "management_fee":
                continue
            if row["tier_label"] == "standard":
                standard = Decimal(row["amount_toman"])
            elif row["tier_label"] == "premium":
                premium = Decimal(row["amount_toman"])
            elif row["tier_label"] == "standard_node":
                standard_node = Decimal(row["amount_toman"])
            elif row["tier_label"] == "premium_node":
                premium_node = Decimal(row["amount_toman"])

    return KaasTariffs(
        cpu_toman=cpu,
        ram_toman=ram,
        storage_toman=storage,
        fee_tiers=tuple(sorted(tiers, key=lambda tier: tier.lower)),
        standard_fee_toman=standard,
        premium_fee_toman=premium,
        standard_node_fee_toman=standard_node,
        premium_node_fee_toman=premium_node,
    )


def _missing_fee_note(offering: Offering) -> str:
    if offering.fee_mode == "kubit_ladder":
        return "کوبیت برای این اندازه (P ≥ ۸۰۰۰) فقط «تماس بگیرید» اعلام کرده است"
    return "هزینه مدیریت برای این اندازه در دسترس نیست"


def _cost_for(
    offering: Offering, tariffs: KaasTariffs, nodes: int, vcpu: int,
    ram_gb: Decimal, disk_gb: Decimal, control_plane: Decimal, benchmarks,
) -> KaasCost:
    if offering.fee_mode == "config_ladder":
        return hamravesh_cost(vcpu, ram_gb, disk_gb, tariffs, control_plane)
    if offering.fee_mode == "kubit_ladder":
        return kubit_cost(vcpu, ram_gb, disk_gb, tariffs, control_plane)
    return sotoon_cost(
        vcpu, nodes, ram_gb, disk_gb, tariffs, control_plane,
        benchmarks.sotoon_premium_min_nodes,
    )


def build_kaas_view(repo: Repository, scenario_key: str | None = None) -> dict:
    benchmarks = load_benchmarks().kaas
    if not benchmarks.scenarios:
        raise ValueError("benchmarks.yaml defines no kaas.scenarios")
    if scenario_key not in benchmarks.scenarios:
        scenario_key = next(iter(benchmarks.scenarios))

    rate_rows = {slug: _rates_for(repo, slug) for slug in ("hamravesh", "kubit", "sotoon")}
    tariffs = {
        offering.key: _tariffs(rate_rows[offering.provider_slug][0], offering, benchmarks)
        for offering in OFFERINGS
    }
    manual_entry = next(
        (entry for entry in repo.freshness("kaas") if entry["provider"] == "Sotoon"),
        None,
    )

    rows_by_scenario: dict[str, list[KaasRow]] = {}
    for key, scenario in benchmarks.scenarios.items():
        scenario_rows: list[KaasRow] = []
        vcpu = scenario.total_vcpu
        ram_gb = Decimal(vcpu) * benchmarks.ram_per_vcpu_gb
        disk_gb = Decimal(vcpu) * benchmarks.disk_per_vcpu_gb
        for offering in OFFERINGS:
            notes: list[str] = []
            tariffs_for_offering = tariffs[offering.key]
            if tariffs_for_offering is None:
                notes.append("نرخ منابع این تأمین‌کننده هنوز گردآوری نشده است")
                scenario_rows.append(KaasRow(
                    key=offering.key, provider_name=offering.name, basis="missing",
                    nodes=scenario.nodes, vcpu=vcpu, ram_gb=ram_gb, disk_gb=disk_gb,
                    management_toman=None, worker_toman=None,
                    control_plane_toman=None, total_toman=None,
                    fee_label="", notes=notes,
                ))
                continue

            control_plane = benchmarks.control_plane_toman.get(offering.key, Decimal(0))
            cost = _cost_for(
                offering, tariffs_for_offering, scenario.nodes, vcpu,
                ram_gb, disk_gb, control_plane, benchmarks,
            )
            basis = offering.basis if cost.total_toman is not None else "missing"
            fee_label = ""
            if offering.fee_mode == "sotoon_nodes":
                fee_label = (
                    "استاندارد" if scenario.nodes < benchmarks.sotoon_premium_min_nodes
                    else "پریمیوم"
                )
                notes.append(f"اشتراک {fee_label}")
                notes.append("مدیریت = اشتراک + هزینه هر نود")
            if cost.management_toman is None:
                notes.append(_missing_fee_note(offering))
            if offering.key == "hamravesh_v1":
                notes.append(ROW_NOTE_V1)
            elif offering.key == "hamravesh_v2":
                notes.append(ROW_NOTE_V2)
            provenance = "live"
            if offering.key == "sotoon":
                provenance = "manual"
                if manual_entry and manual_entry.get("source_document"):
                    valid = (
                        f" · معتبر تا {format_jalali(manual_entry['valid_until'], with_time=False)}"
                        if manual_entry.get("valid_until") else ""
                    )
                    notes.append(
                        f"منبع دستی: {manual_entry['source_document']}{valid}"
                    )
            scenario_rows.append(KaasRow(
                key=offering.key,
                provider_name=offering.name,
                basis=basis,
                nodes=scenario.nodes,
                vcpu=vcpu,
                ram_gb=ram_gb,
                disk_gb=disk_gb,
                management_toman=cost.management_toman,
                worker_toman=cost.worker_toman,
                control_plane_toman=cost.control_plane_toman,
                total_toman=cost.total_toman,
                fee_label=fee_label,
                notes=notes,
                observed_at=rate_rows[offering.provider_slug][1],
                provenance=provenance,
            ))
        rows_by_scenario[key] = scenario_rows

    def chart_for(field_name: str) -> list[dict]:
        values = [
            row for row in rows_by_scenario[scenario_key]
            if getattr(row, field_name) is not None
        ]
        max_value = max((getattr(row, field_name) for row in values), default=None)
        chart: list[dict] = []
        if not max_value:
            return chart
        for row in sorted(values, key=lambda item: getattr(item, field_name)):
            value = getattr(row, field_name)
            chart.append({
                "provider_name": row.provider_name,
                "basis": row.basis,
                "plan_name": row.provider_name,
                "price": value,
                "width_pct": max(int(value / max_value * 100), 2),
            })
        for row in rows_by_scenario[scenario_key]:
            if getattr(row, field_name) is None:
                chart.append({
                    "provider_name": row.provider_name,
                    "basis": "missing", "plan_name": row.provider_name,
                    "price": None, "width_pct": 0,
                })
        return chart

    def matrix_for(field_name: str) -> list[dict]:
        return [
            {
                "provider_name": offering.name,
                "cells": [
                    {
                        "key": key,
                        "value": getattr(
                            next(row for row in rows_by_scenario[key] if row.key == offering.key),
                            field_name,
                        ),
                    }
                    for key in benchmarks.scenarios
                ],
            }
            for offering in OFFERINGS
        ]

    selected = benchmarks.scenarios[scenario_key]
    return {
        "scenario": scenario_key,
        "scenario_label": selected.label,
        "scenarios": [
            {
                "key": key,
                "label": value.label,
                "nodes": value.nodes,
                "vcpu_per_node": value.vcpu_per_node,
                "total_vcpu": value.total_vcpu,
            }
            for key, value in benchmarks.scenarios.items()
        ],
        "target": {
            "nodes": selected.nodes,
            "vcpu_per_node": selected.vcpu_per_node,
            "vcpu": selected.total_vcpu,
            "ram_gb": Decimal(selected.total_vcpu) * benchmarks.ram_per_vcpu_gb,
            "disk_gb": Decimal(selected.total_vcpu) * benchmarks.disk_per_vcpu_gb,
        },
        "rows": rows_by_scenario[scenario_key],
        "chart": chart_for("total_toman"),
        "fee_chart": chart_for("management_toman"),
        "matrix": matrix_for("total_toman"),
        "fee_matrix": matrix_for("management_toman"),
        "monthly_hours": benchmarks.monthly_hours,
        "provider_notes": [
            PROVIDER_NOTE_1, PROVIDER_NOTE_2, PROVIDER_NOTE_KUBIT, PROVIDER_NOTE_SOTOON,
        ],
        "notes": GENERAL_NOTES,
    }
