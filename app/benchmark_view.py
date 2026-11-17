"""Object Storage performance comparison from the offline benchmark package.

Display-only: the long-format dataset stays the single source of truth and this
module selects one value per provider for the metrics the report itself
tabulates. No values are computed or inferred.
"""
from __future__ import annotations

from decimal import Decimal

from comparison.benchmarks import load_observations, pivot_observations
from util.format import to_persian_digits
from util.jalali import format_jalali

PROVIDERS = ("Hamravesh", "Arvan", "Sotoon", "Kubit")

# The comparison rows tabulated by the report: (workload, metric, object size).
CURATED = (
    ("PUT", "throughput", "512KiB"),
    ("PUT", "operation_rate", "512KiB"),
    ("PUT", "latency_p50", "512KiB"),
    ("PUT", "latency_p99", "512KiB"),
    ("PUT", "ttfb_p50", "512KiB"),
    ("GET", "throughput", "512KiB"),
    ("GET", "latency_p50", "512KiB"),
    ("GET", "latency_p99", "512KiB"),
    ("GET", "ttfb_p50", "512KiB"),
    ("MIXED", "throughput", "512KiB"),
    ("MIXED", "operation_rate", "512KiB"),
    ("LIST", "operation_rate", "10KiB"),
    ("LIST", "latency_p50", "10KiB"),
    ("STAT", "operation_rate", "10KiB"),
    ("STAT", "latency_p50", "10KiB"),
    ("DELETE", "operation_rate", "10KiB"),
    ("DELETE", "latency_p99", "10KiB"),
)

METRIC_LABELS = {
    "throughput": ("توان عملیاتی", "throughput"),
    "operation_rate": ("نرخ عملیات", "operation rate"),
    "latency_p50": ("تأخیر میانه", "latency p50"),
    "latency_p99": ("تأخیر صدک ۹۹", "latency p99"),
    "ttfb_p50": ("زمان تا اولین بایت", "TTFB p50"),
}
UNITS = {
    "throughput": "MiB/s",
    "operation_rate": "obj/s",
    "latency_p50": "ms",
    "latency_p99": "ms",
    "ttfb_p50": "ms",
}
HIGHER_IS_BETTER = {"throughput", "operation_rate"}
WORKLOADS = ("PUT", "GET", "MIXED", "LIST", "STAT", "DELETE")
SIZE_LABELS = {"512KiB": "۵۱۲KiB", "10KiB": "۱۰KiB"}

NOTES = [
    "منبع: بسته‌ی آفلاین بنچمارک نسخه ۶ (مهر ۱۴۰۵)، ابزار MinIO Warp؛ "
    "فایل benchmark/observations.csv در datasets/offline/object-storage-benchmark-v6",
    "چهار تأمین‌کننده در یک آزمون کنترل‌شده‌ی واحد اندازه‌گیری نشده‌اند: "
    "Hamravesh، Sotoon و Kubit در ۲۷ سپتامبر ۲۰۲۶ و Arvan در ۱۲–۱۳ اوت ۲۰۲۶. "
    "این جدول یک نمایش مقایسه‌ای است، نه رتبه‌بندی کلی؛ مقایسه‌ی معتبر فقط درون هر نشست است.",
    "هر خانه یک عدد است: میانه‌ی سه اجرا وقتی موجود باشد، وگرنه مقدار گزارش‌شده یا اجرای تک.",
    "اندازه‌ی شیء: ۵۱۲KiB برای PUT/GET/MIXED و ۱۰KiB برای LIST/STAT/DELETE؛ هم‌زمانی ۴.",
    "Sotoon روی endpoint آرشیو و باکت سرد اندازه‌گیری شده؛ طبقه‌ی ذخیره‌سازی با بقیه یکسان نیست.",
    "Arvan در LIST بیست‌وسه خطای SlowDown داشته و p50 آن در گزارش بعداً از حدود ۳٬۲۴۳ به "
    "حدود ۵۷۵ میلی‌ثانیه اصلاح شده است.",
    "GET در ۲۷ سپتامبر (حدود ۱۹٫۶ MiB/s) نزدیک سقف پهنای باند کلاینت است؛ سقف تأمین‌کننده نیست.",
    "آزمایش مسیر شبکه (Hamravesh مستقیم/پروکسی)، جاروب اندازه‌ی ۶۴KiB و 4MiB و "
    "تشخیص‌های تک‌مرحله‌ای در این جدول نیامده‌اند.",
    "عدد پررنگ بهترین مقدار همان ردیف است (بیشترین برای توان عملیاتی و نرخ عملیات، کمترین "
    "برای تأخیر و TTFB)؛ ردیفی که کمتر از دو مقدار دارد پررنگ نمی‌شود.",
    "«—» یعنی گزارش برای آن تأمین‌کننده در آن سنجه عدد جدول‌بندی‌شده ندارد؛ صفر نیست.",
]


def _run_for(provider: str, workload: str) -> str | None:
    """Each provider's value comes from the session where it was measured."""
    if provider == "Arvan":
        return "2026-08-12-put-arvan-hs3" if workload == "PUT" else "2026-08-13-arvan-hs3"
    if provider in {"Hamravesh", "Sotoon", "Kubit"}:
        return "2026-09-27-trio"
    return None


def _format_value(value: Decimal) -> str:
    text = f"{value.normalize():f}"
    whole, _, fraction = text.partition(".")
    fraction = fraction.rstrip("0")
    grouped = f"{int(whole):,}".replace(",", "٬")
    # Persian decimal separator, matching the thousand separator style
    return to_persian_digits(grouped + (f"٫{fraction}" if fraction else ""))


def _date_label(dates: list[str]) -> str:
    formatted = sorted({format_jalali(date, with_time=False) for date in dates})
    if not formatted:
        return ""
    if len(formatted) == 1:
        return formatted[0]
    prefix = formatted[0].rsplit("/", 1)[0]
    if all(item.rsplit("/", 1)[0] == prefix for item in formatted):
        days = "–".join(item.rsplit("/", 1)[1] for item in formatted)
        return f"{prefix}/{days}"
    return " – ".join(formatted)


def build_os_benchmark_view() -> dict:
    observations = load_observations()
    pivoted = pivot_observations(observations, _run_for)
    lookup = {
        (row["workload"], row["metric"], row["object_size"], provider): entry
        for row in pivoted
        for provider, entry in row["providers"].items()
    }

    groups = []
    dates: dict[str, set[str]] = {provider: set() for provider in PROVIDERS}
    for workload in WORKLOADS:
        keys = [key for key in CURATED if key[0] == workload]
        if not keys:
            continue
        rows = []
        for _, metric, object_size in keys:
            values = {}
            for provider in PROVIDERS:
                entry = lookup.get((workload, metric, object_size, provider))
                values[provider] = entry["value"] if entry else None
                if entry:
                    dates[provider].add(entry["test_date"])
            present = [value for value in values.values() if value is not None]
            best = None
            if len(present) >= 2:
                best = max(present) if metric in HIGHER_IS_BETTER else min(present)
            label_fa, label_en = METRIC_LABELS[metric]
            rows.append({
                "label": label_fa,
                "key": label_en,
                "unit": UNITS[metric],
                "cells": [
                    {
                        "provider": provider,
                        "text": _format_value(values[provider]) if values[provider] is not None else "—",
                        "best": best is not None and values[provider] == best,
                    }
                    for provider in PROVIDERS
                ],
            })
        groups.append({
            "label": f"{workload} — شیء {SIZE_LABELS[object_size]}",
            "rows": rows,
        })

    return {
        "providers": [
            {
                "name": provider,
                "date_label": _date_label(sorted(dates[provider])),
            }
            for provider in PROVIDERS
        ],
        "groups": groups,
        "notes": NOTES,
    }
