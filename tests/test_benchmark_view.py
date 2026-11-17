"""Object Storage performance table built from the offline benchmark package."""

from __future__ import annotations

from app.benchmark_view import build_os_benchmark_view


def row_for(view, workload, key):
    group = next(g for g in view["groups"] if g["label"].startswith(workload))
    return next(r for r in group["rows"] if r["key"] == key)


def cells(row):
    return {cell["provider"]: cell for cell in row["cells"]}


def test_table_has_the_report_comparison_rows():
    view = build_os_benchmark_view()
    assert [p["name"] for p in view["providers"]] == [
        "Hamravesh", "Arvan", "Sotoon", "Kubit",
    ]
    assert [g["label"].split(" —")[0] for g in view["groups"]] == [
        "PUT", "GET", "MIXED", "LIST", "STAT", "DELETE",
    ]
    assert sum(len(g["rows"]) for g in view["groups"]) == 17


def test_provider_headers_show_the_measured_session():
    view = build_os_benchmark_view()
    dates = {p["name"]: p["date_label"] for p in view["providers"]}
    assert dates["Hamravesh"] == "۱۴۰۵/۰۷/۰۵"
    assert dates["Sotoon"] == "۱۴۰۵/۰۷/۰۵"
    assert dates["Kubit"] == "۱۴۰۵/۰۷/۰۵"
    assert dates["Arvan"] == "۱۴۰۵/۰۵/۲۱–۲۲"


def test_values_come_from_the_right_session_and_are_formatted():
    view = build_os_benchmark_view()

    put = cells(row_for(view, "PUT", "throughput"))
    assert put["Arvan"]["text"] == "۱۶٫۴۳"   # August PUT run
    assert put["Hamravesh"]["text"] == "۶٫۹۹"  # 27 Sep trio
    assert put["Sotoon"]["text"] == "۱۳٫۱۲"
    assert put["Kubit"]["text"] == "۶٫۱۷"

    listing = cells(row_for(view, "LIST", "operation rate"))
    assert listing["Hamravesh"]["text"] == "۲۴٬۴۶۱"


def test_best_value_is_flagged_by_metric_direction():
    view = build_os_benchmark_view()

    # higher is better
    assert cells(row_for(view, "PUT", "throughput"))["Arvan"]["best"] is True
    assert cells(row_for(view, "GET", "throughput"))["Hamravesh"]["best"] is True
    assert cells(row_for(view, "LIST", "operation rate"))["Hamravesh"]["best"] is True

    # lower is better
    assert cells(row_for(view, "PUT", "latency p50"))["Arvan"]["best"] is True
    assert cells(row_for(view, "STAT", "latency p50"))["Sotoon"]["best"] is True
    assert cells(row_for(view, "DELETE", "latency p99"))["Hamravesh"]["best"] is True


def test_missing_values_are_dashes_and_never_best():
    view = build_os_benchmark_view()

    put_rate = cells(row_for(view, "PUT", "operation rate"))
    assert put_rate["Hamravesh"]["text"] == "—"
    assert put_rate["Sotoon"]["text"] == "—"
    # only Arvan reported this metric, so nothing is bolded
    assert not any(cell["best"] for cell in put_rate.values())

    mixed_rate = cells(row_for(view, "MIXED", "operation rate"))
    assert mixed_rate["Hamravesh"]["text"] == "—"
    assert not any(cell["best"] for cell in mixed_rate.values())

    list_latency = cells(row_for(view, "LIST", "latency p50"))
    assert list_latency["Arvan"]["text"] == "—"
    assert list_latency["Hamravesh"]["best"] is True


def test_notes_cover_the_known_comparability_traps():
    view = build_os_benchmark_view()
    notes = " ".join(view["notes"])
    for marker in (
        "کنترل‌شده‌ی واحد",
        "میانه‌ی سه اجرا",
        "۵۱۲KiB",
        "endpoint آرشیو",
        "SlowDown",
        "سقف پهنای باند کلاینت",
        "پررنگ",
    ):
        assert marker in notes
