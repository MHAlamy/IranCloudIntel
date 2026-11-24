"""Sotoon Gen2 VM prices from the manually transcribed Spring 1405 price list.

Owner decisions (2026-11-17):
- the Neda datacenter (the middle one) is the comparison region;
- dedicated compute compares as Premium and shared compute as Standard
  (mapping lives in config/tiers.yaml);
- larger configurations are built from the 1 vCPU + 2 GB unit: compute price =
  unit price × vCPU;
- the reference disk uses the دیسک مانا نوع ۲ (premium) class, because Sotoon
  bills disk separately while the other providers include it in their bundles.

The document is offline and manually transcribed, so no network call and no
LLM are involved. Every derived price keeps the source page and the document's
validity window.
"""
from __future__ import annotations

import csv
import json
import re
from decimal import Decimal
from pathlib import Path

from collectors.common import FetchError
from collectors.kaas_pipeline import KaasCollection, KaasRate
from collectors.offline_pipeline import (
    OfflineCollection,
    OfflineOsRate,
    OfflinePlan,
    OfflineRateCollection,
)
from comparison.kaas_pricing import irr_to_toman
from config.loader import SourceConfig, load_benchmarks
from util.format import format_number, format_toman

ROOT = Path(__file__).resolve().parent.parent
UNIT_VCPU = 1
UNIT_RAM_GB = 2
IRR_PER_TOMAN = 10

# Display labels for the disk classes printed in the price list (page 4).
DISK_LABELS = {
    "local_disk": "دیسک محلی",
    "mana_1_standard": "دیسک مانا نوع ۱ (استاندارد)",
    "mana_2_premium": "دیسک مانا نوع ۲ (پرمیوم)",
    "mana_3_ultra": "دیسک مانا نوع ۳ (اولترا)",
    "mana_4_ultra2": "دیسک مانا نوع ۴ (اولترا ۲)",
    "mana_5_ultra3": "دیسک مانا نوع ۵ (اولترا ۳)",
    "mana_6_ultra5": "دیسک مانا نوع ۶ (اولترا ۵)",
}


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
    disk_sku: str, disk_label: str, plans: list[OfflinePlan],
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
        f"Disk {disk_label} ({disk_sku}): {disk_irr:,} IRR/GB-month",
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
    disk_label = DISK_LABELS.get(disk_sku, disk_sku)
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
                    disk_type=disk_label,
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
        cleaned=_cleaned_markdown(manifest, region, units, disk_irr, disk_sku, disk_label, plans),
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
        disk_sku=source.navigation.get("disk_sku", "mana_2_premium"),
        sizes=load_benchmarks().vm.sizes,
    )


# -- Object Storage (HiCap) -------------------------------------------------

_BAND_RE = re.compile(r"^(first|next)_(\d+)_(GB|TB)$")
_ABOVE_RE = re.compile(r"^above_(\d+)_(PB)$")


def _read_os_rows(package: Path) -> list[dict]:
    path = package / "prices" / "object_storage.csv"
    if not path.exists():
        raise FetchError(f"offline package has no Object Storage price file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _toman(irr: int) -> str:
    return str(Decimal(irr) / IRR_PER_TOMAN)


def _band_bounds(label: str, cursor: Decimal, tb_to_gb: int) -> tuple[Decimal, Decimal | None]:
    """Successive-tier bounds from a label such as `next_450_GB` or `above_1_PB`.

    The catalogue mixes GB/TB/PB without saying decimal or binary; `tb_to_gb` is
    the configured assumption (1024). The document's bands are contiguous, so
    each band starts where the previous one ended.
    """
    match = _BAND_RE.match(label)
    if match:
        size = Decimal(match.group(2))
        if match.group(3) == "TB":
            size *= Decimal(tb_to_gb)
        return cursor, cursor + size
    if _ABOVE_RE.match(label):
        return cursor, None
    raise FetchError(f"unsupported Sotoon egress band label: {label!r}")


def _band_label(min_gb: Decimal, max_gb: Decimal | None) -> str:
    if max_gb is None:
        return f"بیش از {format_number(min_gb)} گیگابایت"
    return f"{format_number(min_gb)} تا {format_number(max_gb)} گیگابایت"


def _os_cleaned_markdown(
    manifest: dict, region: str, storage_class: str, rates: list[OfflineOsRate],
) -> str:
    lines = [
        f"# {manifest.get('title', 'Sotoon price list')} (v{manifest.get('catalogue_version', '?')})",
        "",
        f"Object Storage class: {storage_class} · region: {region} · "
        f"valid until {manifest.get('document_cover_valid_until', 'unknown')}",
        "",
        "| category | tier | range | unit | Toman |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rate in rates:
        amount = "رایگان" if rate.is_free else (rate.amount_toman or "—")
        lines.append(
            f"| {rate.category} | {rate.tier_label} | {rate.range_label or '—'} | "
            f"{rate.unit} | {amount} |"
        )
    return "\n".join(lines) + "\n"


def build_os_collection(
    package: Path, region: str, storage_class: str, tb_to_gb: int,
) -> OfflineRateCollection:
    """HiCap capacity, egress bands and request rate for one datacenter."""
    manifest = _read_manifest(package)
    rows = _read_os_rows(package)
    class_rows = [r for r in rows if r["storage_class"] == storage_class]
    if not class_rows:
        raise FetchError(f"Sotoon price list has no {storage_class!r} class")

    capacity = [
        r for r in class_rows
        if r["charge_component"] == "capacity" and r["region"] == region
    ]
    if len(capacity) != 1:
        raise FetchError(
            f"Sotoon {storage_class} {region} capacity rows: expected 1, got {len(capacity)}"
        )
    capacity_row = capacity[0]
    capacity_irr = int(capacity_row["price_irr"])
    rates = [
        OfflineOsRate(
            category="storage",
            unit="هر گیگابایت",
            tier_label=storage_class,
            range_label="",
            range_min_gb=None,
            range_max_gb=None,
            amount_toman=_toman(capacity_irr),
            is_free=False,
            evidence=(
                f"Sotoon price list v{manifest.get('catalogue_version', '?')} "
                f"p.{capacity_row['source_pdf_page']} ({region}, {storage_class}): "
                f"capacity {capacity_irr:,} IRR/GB-month"
            ),
        )
    ]

    cursor = Decimal(0)
    egress = [r for r in class_rows if r["charge_component"] == "egress_band"]
    if not egress:
        raise FetchError(f"Sotoon {storage_class} publishes no egress bands")
    for row in egress:
        label = (row["notes"] or "").strip()
        low, high = _band_bounds(label, cursor, tb_to_gb)
        cursor = high if high is not None else cursor
        irr = int(row["price_irr"])
        rates.append(
            OfflineOsRate(
                category="traffic",
                unit="هر گیگابایت",
                tier_label=storage_class,
                range_label=_band_label(low, high),
                range_min_gb=str(low),
                range_max_gb=str(high) if high is not None else None,
                amount_toman=_toman(irr),
                is_free=False,
                evidence=(
                    f"Sotoon price list v{manifest.get('catalogue_version', '?')} "
                    f"p.{row['source_pdf_page']} ({storage_class} egress, {label}): "
                    f"{irr:,} IRR/GB"
                ),
            )
        )

    requests = [r for r in class_rows if r["charge_component"] == "requests"]
    if len(requests) != 1:
        raise FetchError(
            f"Sotoon {storage_class} request rows: expected 1, got {len(requests)}"
        )
    request_row = requests[0]
    request_irr = int(request_row["price_irr"])
    rates.append(
        OfflineOsRate(
            category="requests",
            unit="هر ۱۰۰۰ درخواست",
            tier_label=storage_class,
            range_label="",
            range_min_gb=None,
            range_max_gb=None,
            amount_toman=_toman(request_irr),
            is_free=False,
            evidence=(
                f"Sotoon price list v{manifest.get('catalogue_version', '?')} "
                f"p.{request_row['source_pdf_page']} ({storage_class} requests): "
                f"{request_irr:,} IRR per 1,000 requests"
            ),
        )
    )

    return OfflineRateCollection(
        rates=rates,
        source_document=f"Sotoon price list v{manifest.get('catalogue_version', '?')} (Spring 1405)",
        valid_until=manifest.get("valid_until"),
        cleaned=_os_cleaned_markdown(manifest, region, storage_class, rates),
        extra_files={
            "manifest.json": (package / "manifest.json").read_text(encoding="utf-8"),
            "source_object_storage.csv": (
                package / "prices" / "object_storage.csv"
            ).read_text(encoding="utf-8-sig"),
        },
    )


def collect_sotoon_os_offline(source: SourceConfig) -> OfflineRateCollection:
    benchmarks = load_benchmarks().object_storage
    return build_os_collection(
        package=ROOT / source.url,
        region=source.navigation.get("region", "Neda"),
        storage_class=source.navigation.get("storage_class", "HiCap"),
        tb_to_gb=benchmarks.tb_to_gb,
    )


# -- DBaaS ------------------------------------------------------------------

DBAAS_CLASSES = {
    # Class A: dedicated CPU bundle + local disk.
    "local": {
        "allocation": "dedicated",
        "disk_label": "دیسک محلی",
        "label": "محلی/پرمیوم",
    },
    # Class B: shared (E-series) CPU bundle + premium network disk.
    "shared": {
        "allocation": "shared",
        "disk_label": "دیسک مانا نوع ۲ (پرمیوم)",
        "label": "اشتراکی/شبکه",
    },
}


def _read_dbaas_rows(package: Path) -> list[dict]:
    path = package / "prices" / "dbaas_gen2.csv"
    if not path.exists():
        raise FetchError(f"offline package has no DBaaS price file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_dbaas_collection(
    package: Path, region: str, local_disk_sku: str, network_disk_sku: str,
    sizes: dict,
) -> OfflineCollection:
    """Derive every reference size from Sotoon's published Gen2 price list.

    Sotoon publishes 1 vCPU + 2 GB DBaaS compute bundles. Larger references
    are calculated with the owner-approved stacking rule: unit price × vCPU
    (RAM scales at 2 GB per vCPU), plus the selected disk at its GB-month rate.
    """
    manifest = _read_manifest(package)
    rows = _read_dbaas_rows(package)
    disk_skus = {"local": local_disk_sku, "shared": network_disk_sku}
    disk_rates = {
        row["sku"]: (int(row["price_irr"]), int(row["source_pdf_page"]))
        for row in rows
        if row["component"] == "db_disk"
    }
    for sku in disk_skus.values():
        if sku not in disk_rates:
            raise FetchError(f"Sotoon DBaaS price list has no disk SKU {sku!r}")

    plans: list[OfflinePlan] = []
    for size in sizes.values():
        for class_key, config in DBAAS_CLASSES.items():
            bundles = [
                row for row in rows
                if row["component"] == "db_compute_bundle"
                and row["region"] == region
                and row["cpu_allocation"] == config["allocation"]
            ]
            exact = [
                row for row in bundles
                if int(row["vcpu"]) == size.vcpu
                and int(row["ram_gb"]) == size.ram_gb
            ]
            if exact:
                if len(exact) != 1:
                    raise FetchError(
                        f"Sotoon {region} DBaaS {size.vcpu} vCPU + {size.ram_gb} GB "
                        f"{config['allocation']} bundles: expected 1, got {len(exact)}"
                    )
                compute_row = exact[0]
                units = 1
            else:
                unit = [
                    row for row in bundles
                    if int(row["vcpu"]) == UNIT_VCPU
                    and int(row["ram_gb"]) == UNIT_RAM_GB
                ]
                if not unit:
                    continue
                if len(unit) != 1:
                    raise FetchError(
                        f"Sotoon {region} DBaaS {config['allocation']} base bundle: "
                        f"expected 1, got {len(unit)}"
                    )
                if size.ram_gb != UNIT_RAM_GB * size.vcpu:
                    raise FetchError(
                        f"reference size {size.vcpu} vCPU + {size.ram_gb} GB is not "
                        f"a multiple of the {UNIT_VCPU} vCPU + {UNIT_RAM_GB} GB unit"
                    )
                compute_row = unit[0]
                units = size.vcpu // UNIT_VCPU

            disk_sku = disk_skus[class_key]
            disk_irr, disk_page = disk_rates[disk_sku]
            unit_irr = int(compute_row["price_irr"])
            compute_irr = unit_irr * units
            disk_total_irr = disk_irr * size.disk_gb
            total_irr = compute_irr + disk_total_irr
            price_toman = Decimal(total_irr) / IRR_PER_TOMAN
            plans.append(
                OfflinePlan(
                    plan_name=(
                        f"{size.vcpu} vCPU + {size.ram_gb} GB ({config['label']})"
                    ),
                    vcpu=size.vcpu,
                    ram_gb=Decimal(size.ram_gb),
                    disk_gb=Decimal(size.disk_gb),
                    price_toman=price_toman,
                    price_raw=f"{format_toman(price_toman)} (محاسبه‌شده)",
                    provider_tier_raw=config["allocation"],
                    region=f"ir-{region.lower()}",
                    product_family=f"dbaas_{class_key}_calculated",
                    pricing_type="configurable_quote",
                    disk_type=config["disk_label"],
                    evidence=(
                        f"Sotoon price list v{manifest.get('catalogue_version', '?')} "
                        f"p.{compute_row['source_pdf_page']} ({region}): "
                        f"{compute_row['sku']} {config['allocation']} "
                        f"{UNIT_VCPU} vCPU + {UNIT_RAM_GB} GB = {unit_irr:,} IRR"
                        + (f" × {units} = {compute_irr:,} IRR; " if units > 1 else "; ")
                        + f"disk p.{disk_page} {size.disk_gb} GB × {disk_irr:,} IRR "
                        f"({disk_sku}) = {disk_total_irr:,} IRR; total {total_irr:,} IRR = "
                        f"{format_toman(price_toman, False)} Toman/month; "
                        f"valid until {manifest.get('document_cover_valid_until', 'unknown')}"
                    ),
                )
            )

    if not plans:
        raise FetchError(f"Sotoon price list has no DBaaS bundles for {region}")

    return OfflineCollection(
        plans=plans,
        source_document=f"Sotoon price list v{manifest.get('catalogue_version', '?')} (Spring 1405)",
        valid_until=manifest.get("valid_until"),
        cleaned=_dbaas_cleaned_markdown(manifest, region, plans),
        extra_files={
            "manifest.json": (package / "manifest.json").read_text(encoding="utf-8"),
            "source_dbaas_gen2.csv": (
                package / "prices" / "dbaas_gen2.csv"
            ).read_text(encoding="utf-8-sig"),
        },
    )


def _dbaas_cleaned_markdown(manifest: dict, region: str, plans: list[OfflinePlan]) -> str:
    lines = [
        f"# {manifest.get('title', 'Sotoon price list')} (v{manifest.get('catalogue_version', '?')})",
        "",
        f"DBaaS region: {region} · valid until "
        f"{manifest.get('document_cover_valid_until', 'unknown')}",
        "",
        "| class | vCPU | RAM GB | disk GB | disk | monthly Toman |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for plan in plans:
        lines.append(
            f"| {plan.product_family} | {plan.vcpu} | {plan.ram_gb} | {plan.disk_gb} | "
            f"{plan.disk_type} | {format_toman(plan.price_toman, False)} |"
        )
    return "\n".join(lines) + "\n"


def collect_sotoon_dbaas_offline(source: SourceConfig) -> OfflineCollection:
    return build_dbaas_collection(
        package=ROOT / source.url,
        region=source.navigation.get("region", "Neda"),
        local_disk_sku=source.navigation.get("local_disk_sku", "local_disk"),
        network_disk_sku=source.navigation.get("network_disk_sku", "mana_2_premium"),
        sizes=load_benchmarks().dbaas.sizes,
    )


# -- Managed Kubernetes -----------------------------------------------------

def _read_kaas_rows(package: Path) -> list[dict]:
    path = package / "prices" / "k8s_gen2.csv"
    if not path.exists():
        raise FetchError(f"offline package has no KaaS price file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_kaas_collection(
    package: Path, region: str, compute_sku: str, disk_sku: str,
) -> KaasCollection:
    """C1 worker compute, local SSD and cluster subscription from the price list.

    The C1 bundle is 1 vCPU + 2 GB. The dashboard's linear scaling assumption
    (C1 price × total vCPU) is applied outside this loader, in the pricing
    module, so the stored tariff remains the published unit price.
    """
    manifest = _read_manifest(package)
    vm_rows = _read_rows(package)
    kaas_rows = _read_kaas_rows(package)

    compute = [
        row for row in vm_rows
        if row["component"] == "compute_bundle"
        and row["region"] == region
        and row["sku"] == compute_sku
        and int(row["vcpu"]) == UNIT_VCPU
        and int(row["ram_gb"]) == UNIT_RAM_GB
    ]
    if len(compute) != 1:
        raise FetchError(
            f"Sotoon {region} KaaS compute unit {compute_sku!r} "
            f"({UNIT_VCPU} vCPU + {UNIT_RAM_GB} GB): expected 1, got {len(compute)}"
        )
    disk = [
        row for row in vm_rows
        if row["component"] == "disk"
        and row["region"] == region
        and row["sku"] == disk_sku
    ]
    if len(disk) != 1:
        raise FetchError(
            f"Sotoon {region} KaaS disk {disk_sku!r}: expected 1, got {len(disk)}"
        )

    compute_row, disk_row = compute[0], disk[0]
    compute_toman = irr_to_toman(compute_row["price_irr"])
    disk_toman = irr_to_toman(disk_row["price_irr"])
    rates = [
        KaasRate(
            category="cpu",
            unit="هر vCPU",
            tier_label=compute_sku,
            amount_toman=str(compute_toman),
            evidence=(
                f"Sotoon price list v{manifest.get('catalogue_version', '?')} "
                f"p.{compute_row['source_pdf_page']} ({region}): {compute_sku} "
                f"{UNIT_VCPU} vCPU + {UNIT_RAM_GB} GB = "
                f"{int(compute_row['price_irr']):,} IRR = "
                f"{format_toman(compute_toman, False)} Toman/month"
            ),
            region="iran",
        ),
        KaasRate(
            category="storage",
            unit="هر گیگابایت",
            tier_label=disk_sku,
            amount_toman=str(disk_toman),
            evidence=(
                f"Sotoon price list v{manifest.get('catalogue_version', '?')} "
                f"p.{disk_row['source_pdf_page']} ({region}): {disk_sku} = "
                f"{int(disk_row['price_irr']):,} IRR/GB-month = "
                f"{format_toman(disk_toman, False)} Toman/GB-month"
            ),
            region="iran",
        ),
    ]

    subscriptions = [
        row for row in kaas_rows if row["sku"] == "cluster_subscription"
    ]
    for row in subscriptions:
        family = row["family"]
        amount = irr_to_toman(row["price_irr"])
        rates.append(
            KaasRate(
                category="management_fee",
                unit="ماهانه",
                tier_label=family,
                amount_toman=str(amount),
                evidence=(
                    f"Sotoon price list p.{row['source_pdf_page']}: {family} "
                    f"cluster subscription = {int(row['price_irr']):,} IRR = "
                    f"{format_toman(amount, False)} Toman/month"
                ),
                region="iran",
            )
        )
    node_fees = [
        row for row in kaas_rows if row["sku"] == "node_maintenance"
    ]
    for row in node_fees:
        family = row["family"]
        amount = irr_to_toman(row["price_irr"])
        rates.append(
            KaasRate(
                category="management_fee",
                unit="هر نود در ماه",
                tier_label=f"{family}_node",
                amount_toman=str(amount),
                evidence=(
                    f"Sotoon price list p.{row['source_pdf_page']}: {family} "
                    f"per-node management fee = {int(row['price_irr']):,} IRR = "
                    f"{format_toman(amount, False)} Toman/node-month"
                ),
                region="iran",
            )
        )
    for label, rows_for_fee in (("subscriptions", subscriptions), ("node fees", node_fees)):
        if {row["family"] for row in rows_for_fee} != {"standard", "premium"}:
            raise FetchError(f"Sotoon KaaS standard/premium {label} missing")

    cleaned_lines = [
        f"# {manifest.get('title', 'Sotoon price list')} "
        f"(v{manifest.get('catalogue_version', '?')})",
        "",
        f"KaaS region: {region} · worker {compute_sku} · disk {disk_sku} · "
        f"valid until {manifest.get('document_cover_valid_until', 'unknown')}",
        "",
        "| category | tier | unit | monthly Toman |",
        "| --- | --- | --- | --- |",
    ]
    for rate in rates:
        cleaned_lines.append(
            f"| {rate.category} | {rate.tier_label} | {rate.unit} | "
            f"{format_toman(rate.amount_toman, False)} |"
        )
    cleaned_lines += [
        "",
        "Cluster management = subscription + nodes × per-node fee. Extra "
        "control-plane-core tariffs remain excluded.",
    ]

    return KaasCollection(
        rates=rates,
        cleaned="\n".join(cleaned_lines) + "\n",
        source_document=(
            f"Sotoon price list v{manifest.get('catalogue_version', '?')} (Spring 1405)"
        ),
        valid_until=manifest.get("valid_until"),
        extra_files={
            "manifest.json": (package / "manifest.json").read_text(encoding="utf-8"),
            "source_k8s_gen2.csv": (
                package / "prices" / "k8s_gen2.csv"
            ).read_text(encoding="utf-8-sig"),
            "source_vm_gen2.csv": (
                package / "prices" / "vm_gen2.csv"
            ).read_text(encoding="utf-8-sig"),
        },
    )


def collect_sotoon_kaas_offline(source: SourceConfig) -> KaasCollection:
    return build_kaas_collection(
        package=ROOT / source.url,
        region=source.navigation.get("region", "Neda"),
        compute_sku=source.navigation.get("compute_sku", "C1"),
        disk_sku=source.navigation.get("disk_sku", "local_disk"),
    )
