"""Object Storage benchmark observations: loading and display pivots.

The committed dataset keeps only the long-format `observations.csv`. A wide
table (one column group per provider) is presentation, so it is built here at
display time; storing a second copy would create two sources of truth that can
drift apart.

The providers were not measured in one controlled experiment, so a pivot must
say which run each provider's value comes from — `run_for(provider, workload)`
does that explicitly and never guesses.
"""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGE = ROOT / "datasets" / "offline" / "object-storage-benchmark-v6"

WORKLOAD_ORDER = ("PUT", "GET", "MIXED", "LIST", "STAT", "DELETE", "DIAGNOSTIC")
METRIC_ORDER = (
    "throughput",
    "operation_rate",
    "latency_p50",
    "latency_p90",
    "latency_p99",
    "ttfb_p50",
    "latency_min",
    "latency_max",
    "requests_total",
    "errors_total",
    "duration_total",
)

RunFor = Callable[[str, str], "str | None"]


def load_observations(package: Path = DEFAULT_PACKAGE) -> list[dict]:
    """Read the long-format benchmark table (one row per measurement)."""
    path = package / "benchmark" / "observations.csv"
    if not path.exists():
        raise FileNotFoundError(f"benchmark observations not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["value"] = Decimal(row["value"])
    return rows


def _sort_key(row: dict) -> tuple:
    workload = row["workload"]
    metric = row["metric"]
    return (
        WORKLOAD_ORDER.index(workload) if workload in WORKLOAD_ORDER else len(WORKLOAD_ORDER),
        METRIC_ORDER.index(metric) if metric in METRIC_ORDER else len(METRIC_ORDER),
        metric,
        row["object_size"],
        row["unit"],
    )


def pivot_observations(
    observations: Iterable[dict], run_for: RunFor,
) -> list[dict]:
    """Wide, display-only rows: one per workload, metric and object size.

    Each provider column keeps its own `run_id`, date and source page, so a
    cross-session table can never be mistaken for a single controlled run.
    """
    table: dict[tuple, dict] = {}
    for obs in observations:
        run_id = run_for(obs["provider"], obs["workload"])
        if run_id is None or obs["run_id"] != run_id:
            continue
        key = (obs["workload"], obs["metric"], obs["object_size"], obs["unit"])
        row = table.setdefault(
            key,
            {
                "workload": obs["workload"],
                "metric": obs["metric"],
                "object_size": obs["object_size"],
                "unit": obs["unit"],
                "providers": {},
            },
        )
        row["providers"][obs["provider"]] = {
            "value": obs["value"],
            "run_id": obs["run_id"],
            "test_date": obs["test_date"],
            "source_pdf_page": obs["source_pdf_page"],
            "aggregation": obs["aggregation"],
        }
    return sorted(table.values(), key=_sort_key)
