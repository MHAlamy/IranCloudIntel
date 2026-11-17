"""Object Storage benchmark pivot: the long table is the only stored source."""

from __future__ import annotations

from decimal import Decimal

from comparison.benchmarks import load_observations, pivot_observations

# The historical wide table mixed sessions: Arvan from August, the rest from
# the 27 September trio. The pivot must reproduce exactly that selection.
def historical_run(provider: str, workload: str) -> str | None:
    if provider == "Arvan":
        return "2026-08-12-put-arvan-hs3" if workload == "PUT" else "2026-08-13-arvan-hs3"
    if provider in {"Hamravesh", "Kubit", "Sotoon"}:
        return "2026-09-27-trio"
    return None


def row_for(rows, workload, metric, size):
    return next(
        r for r in rows
        if r["workload"] == workload and r["metric"] == metric and r["object_size"] == size
    )


CURATED_KEYS = {
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
}


def test_pivot_reproduces_the_wide_overview():
    rows = pivot_observations(load_observations(), historical_run)
    by_key = {(r["workload"], r["metric"], r["object_size"]): r for r in rows}
    # The old curated overview is a subset of the long table; the pivot exposes
    # every measured metric, so the display layer picks what it shows.
    assert CURATED_KEYS <= set(by_key)
    assert len(rows) > len(CURATED_KEYS)  # run ranges and diagnostics are kept too

    put = by_key[("PUT", "throughput", "512KiB")]
    assert put["unit"] == "MiB/s"
    assert {p: v["value"] for p, v in put["providers"].items()} == {
        "Hamravesh": Decimal("6.99"),
        "Arvan": Decimal("16.43"),
        "Kubit": Decimal("6.17"),
        "Sotoon": Decimal("13.12"),
    }

    get = by_key[("GET", "throughput", "512KiB")]
    assert get["providers"]["Hamravesh"]["value"] == Decimal("19.65")
    assert get["providers"]["Sotoon"]["value"] == Decimal("19.61")

    listing = by_key[("LIST", "operation_rate", "10KiB")]
    assert listing["providers"]["Hamravesh"]["value"] == Decimal("24461")
    assert listing["providers"]["Kubit"]["value"] == Decimal("423")

    delete = by_key[("DELETE", "operation_rate", "10KiB")]
    assert delete["providers"]["Arvan"]["value"] == Decimal("117")
    assert delete["providers"]["Sotoon"]["value"] == Decimal("59.2")


def test_pivot_keeps_each_providers_own_run_and_page():
    rows = pivot_observations(load_observations(), historical_run)
    put = row_for(rows, "PUT", "throughput", "512KiB")
    assert put["providers"]["Arvan"]["run_id"] == "2026-08-12-put-arvan-hs3"
    assert put["providers"]["Arvan"]["test_date"] == "2026-08-12"
    assert put["providers"]["Hamravesh"]["run_id"] == "2026-09-27-trio"
    assert put["providers"]["Hamravesh"]["source_pdf_page"] == "12"

    get = row_for(rows, "GET", "throughput", "512KiB")
    assert get["providers"]["Arvan"]["run_id"] == "2026-08-13-arvan-hs3"


def test_pivot_omits_providers_without_a_selected_run():
    rows = pivot_observations(
        load_observations(),
        lambda provider, workload: "2026-09-27-trio" if provider == "Sotoon" else None,
    )
    assert rows
    assert {p for row in rows for p in row["providers"]} == {"Sotoon"}


def test_no_derived_overview_file_is_stored():
    from comparison.benchmarks import DEFAULT_PACKAGE

    assert not (DEFAULT_PACKAGE / "derived").exists()
