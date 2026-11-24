"""KaaS source parsers: Hamravesh, Kubit and Sotoon offline."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from collectors.hamravesh_kaas import parse_hamravesh_kaas
from collectors.kubit_kaas import parse_kubit_kaas
from collectors.sotoon_offline import build_kaas_collection

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PACKAGE = ROOT / "datasets" / "offline" / "sotoon-price-1405-v3"


def test_hamravesh_worker_rates_and_fee_bands():
    html = (FIXTURES / "kaas" / "hamravesh_rates.html").read_text(encoding="utf-8")
    rates = parse_hamravesh_kaas(html)
    resources = {r.category: Decimal(r.amount_toman) for r in rates if r.category != "management_fee"}
    assert resources == {
        "cpu": Decimal("595000"),
        "ram": Decimal("290000"),
        "storage": Decimal("16500"),
    }
    fees = {r.tier_label: Decimal(r.amount_toman) for r in rates if r.category == "management_fee"}
    assert fees == {
        "0-200": Decimal("30000000"),
        "200-800": Decimal("80000000"),
        "800-1500": Decimal("150000000"),
    }
    assert "1500-" not in fees  # quote-only band is not invented


def test_kubit_worker_rates_and_licence_ladder():
    html = (FIXTURES / "object_storage" / "kubit_pricing.html").read_text(encoding="utf-8")
    rates = parse_kubit_kaas(html)
    workers = {(r.category, r.tier_label): Decimal(r.amount_toman) for r in rates}
    assert workers[("cpu", "gen-4")] == Decimal("359500")
    assert workers[("ram", "gen-4")] == Decimal("279510")
    assert workers[("storage", "")] == Decimal("14900")
    fees = {r.tier_label: Decimal(r.amount_toman) for r in rates if r.category == "management_fee"}
    assert fees["0-65"] == Decimal("5510000")
    assert fees["65-200"] == Decimal("14500000")
    assert fees["4000-8000"] == Decimal("177300000")
    assert "8000-" not in fees


def test_sotoon_uses_neda_c1_local_disk_and_management_fees():
    collection = build_kaas_collection(
        PACKAGE, region="Neda", compute_sku="C1", disk_sku="local_disk",
    )
    by_key = {(r.category, r.tier_label): Decimal(r.amount_toman) for r in collection.rates}
    assert by_key[("cpu", "C1")] == Decimal("1870000")
    assert by_key[("storage", "local_disk")] == Decimal("21000")
    assert by_key[("management_fee", "standard")] == Decimal("17000000")
    assert by_key[("management_fee", "premium")] == Decimal("40000000")
    assert by_key[("management_fee", "standard_node")] == Decimal("3100000")
    assert by_key[("management_fee", "premium_node")] == Decimal("3900000")
    assert collection.valid_until == "2027-03-20"
    assert "Sotoon price list" in collection.source_document
    assert any("per-node management fee" in r.evidence for r in collection.rates)
    assert "Cluster management = subscription + nodes" in collection.cleaned
    assert "Neda" in collection.cleaned
    assert "IRR" in collection.rates[0].evidence
