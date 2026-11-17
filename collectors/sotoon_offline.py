"""Sotoon Gen2 VM prices from the manually transcribed Spring 1405 price list.

Owner decisions (2026-11-17):
- the Neda datacenter (the middle one) is the comparison region;
- dedicated compute compares as Premium and shared compute as Standard
  (mapping lives in config/tiers.yaml);
- larger configurations are built from the 1 vCPU + 2 GB unit: compute price =
  unit price × vCPU. The reference disk is added at the documented standard
  disk rate, because Sotoon bills disk separately while the other providers
  include it in their bundles.

The document is offline and manually transcribed, so no network call and no
LLM are involved. Every derived price keeps the source page and the document's
validity window.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

from collectors.common import FetchError
from collectors.offline_pipeline import OfflineCollection, OfflinePlan
from config.loader import SourceConfig, load_benchmarks
from util.format import format_toman

ROOT = Path(__file__).resolve().parent.parent
UNIT_VCPU = 1
UNIT_RAM_GB = 2
IRR_PER_TOMAN = 10


def _read_manifest(package: Path) -> dict:
    path = package / "manifest.json"
    if not path.exists():
        raise FetchError(f"offline package has no manifest: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("source_id") != package.name:
        raise FetchError(
            f"manifest source_id {manifest.get('source_id')!r} does not match package {package.name!r}"
        )
    return manifest


def _read_rows(package: Path) -> list[dict]:
    path = package / "prices" / "vm_gen2.csv"
    if not path.exists():
        raise FetchError(f"offline package has no VM price file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _unit_prices(rows: list[dict], region: str) -> dict[str, dict]:
    """The 1 vCPU + 2 GB bundle for each allocation type in one datacenter."""
    units: dict[str, dict] = {}
    for row in rows:
        if row["component"] != "compute_bundle" or row["region"] != region:
            continue
        if int(row["vcpu"]) != UNIT_VCPU or int(row["ram_gb"]) != UNIT_RAM_GB:
            continue
        allocation = (row.get("cpu_allocation") or "").strip().lower()
        if allocation not in {"shared", "dedicated"}:
            continue
        units[allocation] = row
    missing = {"shared", "dedicated"} - set(units)
    if missing:
        raise FetchError(
            f"Sotoon {region} has no 1 vCPU + 2 GB bundle for: {sorted(missing)}"
        )
    return units


def _disk_rate(rows: list[dict], region: str, sku: str) -> tuple[int, int]:
    """(IRR per GB-month, source page) for the configured disk class."""
    for row in rows:
        if row["component"] == "disk" and row["region"] == region and row["sku"] == sku:
            return int(row["price_irr"]), int(row["source_pdf_page"])
    raise FetchError(f"Sotoon {region} publishes no disk price for {sku!r}")


def _cleaned_markdown(
    manifest: dict, region: str, units: dict[str, dict], disk_irr: int,
    disk_sku: str, plans: list[OfflinePlan],
) -> str:
    lines = [
        f"# {manifest.get('title', 'Sotoon price list')} (v{manifest.get('catalogue_version', '?')})",
        "",
        f"Region: {region} · valid until {manifest.get('document_cover_valid_until', 'unknown')}",
        "",
        "| unit | allocation | 1 vCPU + 2 GB (IRR) | source page |",
        "| --- | --- | --- | --- |",
    ]
    for allocation, row in sorted(units.items()):
        lines.append(
            f"| {row['sku']} | {allocation} | {int(row['price_irr']):,} | {row['source_pdf_page']} |"
        )
    lines += [
        "",
        f"Disk {disk_sku}: {disk_irr:,} IRR/GB-month",
        "",
        "## Derived reference sizes",
        "",
        "| vCPU | RAM GB | disk GB | allocation | monthly Toman |",
        "| --- | --- | --- | --- | --- |",
    ]
    for plan in plans:
        lines.append(
            f"| {plan.vcpu} | {plan.ram_gb} | {plan.disk_gb} | {plan.provider_tier_raw} | "
            f"{format_toman(plan.price_toman, False)} |"
        )
    return "\n".join(lines) + "\n"


def build_collection(
    package: Path, region: str, disk_sku: str, sizes: dict,
) -> OfflineCollection:
    """Derive one plan per reference size and allocation from the price list."""
    manifest = _read_manifest(package)
    rows = _read_rows(package)
    units = _unit_prices(rows, region)
    disk_irr, disk_page = _disk_rate(rows, region, disk_sku)
    region_code = f"ir-{region.lower()}"  # Iranian region code, see comparison.matching

    plans: list[OfflinePlan] = []
    for size_key, size in sizes.items():
        if size.ram_gb != UNIT_RAM_GB * size.vcpu:
            raise FetchError(
                f"reference size {size_key!r} is not a multiple of the "
                f"{UNIT_VCPU} vCPU + {UNIT_RAM_GB} GB unit; cannot scale it"
            )
        units_count = size.vcpu // UNIT_VCPU
        for allocation, row in sorted(units.items()):
            unit_irr = int(row["price_irr"])
            compute_irr = unit_irr * units_count
            disk_total_irr = disk_irr * size.disk_gb
            total_irr = compute_irr + disk_total_irr
            price_toman = Decimal(total_irr) / IRR_PER_TOMAN
            plans.append(
                OfflinePlan(
                    plan_name=f"{size.vcpu} vCPU + {size.ram_gb} GB ({allocation})",
                    vcpu=size.vcpu,
                    ram_gb=Decimal(size.ram_gb),
                    disk_gb=Decimal(size.disk_gb),
                    price_toman=price_toman,
                    price_raw=f"{format_toman(price_toman)} (محاسبه‌شده)",
                    provider_tier_raw=allocation,
                    region=region_code,
                    product_family="manual_calculated",
                    pricing_type="configurable_quote",
                    evidence=(
                        f"Sotoon price list v{manifest.get('catalogue_version', '?')} "
                        f"p.{row['source_pdf_page']} ({region}): {row['sku']} {allocation} "
                        f"1 vCPU + 2 GB = {unit_irr:,} IRR; ×{units_count} = {compute_irr:,} IRR; "
                        f"disk p.{disk_page} {size.disk_gb} GB × {disk_irr:,} IRR ({disk_sku}) = "
                        f"{disk_total_irr:,} IRR; total {total_irr:,} IRR = "
                        f"{format_toman(price_toman, False)} Toman/month; "
                        f"valid until {manifest.get('document_cover_valid_until', 'unknown')}"
                    ),
                )
            )

    return OfflineCollection(
        plans=plans,
        source_document=f"Sotoon price list v{manifest.get('catalogue_version', '?')} (Spring 1405)",
        valid_until=manifest.get("valid_until"),
        cleaned=_cleaned_markdown(manifest, region, units, disk_irr, disk_sku, plans),
        extra_files={
            "manifest.json": (package / "manifest.json").read_text(encoding="utf-8"),
            "source_vm_gen2.csv": (package / "prices" / "vm_gen2.csv").read_text(encoding="utf-8-sig"),
        },
    )


def collect_sotoon_offline(source: SourceConfig) -> OfflineCollection:
    package = ROOT / source.url
    return build_collection(
        package=package,
        region=source.navigation.get("region", "Neda"),
        disk_sku=source.navigation.get("disk_sku", "mana_1_standard"),
        sizes=load_benchmarks().vm.sizes,
    )
