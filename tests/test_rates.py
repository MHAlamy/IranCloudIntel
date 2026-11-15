"""Tests for deterministic parsing of Arvan's PAYG rate tables."""

from pathlib import Path

import pytest

from collectors.arvan_rates import RateRow, parse_rates
from comparison.rate_check import load_rate_mappings, verify_bundle
from decimal import Decimal

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arvan_cloud_server"


@pytest.fixture(scope="module")
def rates():
    html = (FIXTURES / "rates_section.html").read_text(encoding="utf-8")
    return parse_rates(html)


def test_parses_all_rate_rows(rates):
    assert len(rates) == 48


def test_iran_cpu_vcore_table(rates):
    by_label = {r.tier_label: r for r in rates if r.category == "cpu" and r.region == "iran"}
    assert by_label["Basic"].amount_toman == "252000"
    assert by_label["Standard"].amount_toman == "327600"
    assert by_label["Premium"].amount_toman == "478800"
    assert by_label["Premium Plus"].amount_toman == "592200"


def test_europe_pane_is_the_x7_6_twin(rates):
    europe_cpu = {r.tier_label: r.amount_toman for r in rates if r.category == "cpu" and r.region == "europe"}
    assert europe_cpu["Basic"] == "294000"  # 252000 * 7/6
    assert europe_cpu["Premium"] == "558600"  # 478800 * 7/6


def test_iran_storage_classes(rates):
    by_label = {r.tier_label: r.amount_toman for r in rates if r.category == "storage" and r.region == "iran"}
    assert by_label["بلاک استوریج (Eco)"] == "18000"
    assert by_label["بلاک استوریج (Hot-SSD)"] == "18000"  # same price as Eco
    assert by_label["بلاک استوریج (Local)"] == "25200"
    assert by_label["بلاک استوریج (Warm)"] == "8640"


def test_ipv4_first_iran(rates):
    ipv4 = [r for r in rates if r.category == "ipv4" and r.region == "iran" and "اول" in r.tier_label]
    assert len(ipv4) == 1 and ipv4[0].amount_toman == "234000"


def test_verification_against_real_bundles(rates):
    """The deterministic verifier must reproduce the 14/14 exact result on real
    Iranian-region bundle prices collected 2026-11-15."""
    mapping = load_rate_mappings()["arvan"]
    rate_rows = [r for r in rates if r.region == "iran"]

    def tier_rates(plan_name: str):
        from comparison.rate_check import TierRates

        family = mapping.family_for(plan_name)
        tier = family["rate_tier"].capitalize()
        cpu = next(r for r in rate_rows if r.category == "cpu" and r.tier_label == tier)
        ram = next(r for r in rate_rows if r.category == "ram" and r.tier_label == tier)
        storage = next(r for r in rate_rows if r.category == "storage" and "Eco" in r.tier_label)
        ipv4 = next(r for r in rate_rows if r.category == "ipv4" and "اول" in r.tier_label)
        return TierRates(
            cpu_rate=Decimal(cpu.amount_toman), ram_rate=Decimal(ram.amount_toman),
            storage_rate=Decimal(storage.amount_toman), ipv4_first=Decimal(ipv4.amount_toman),
        )

    cases = [
        ("eco-small1", 1, 1, 25, "997740", "verified"),
        ("eco-small4", 2, 2, 30, "1401480", "verified"),
        ("g3-small1", 1, 2, 75, "2421720", "verified"),
        ("c2-medium1", 2, 4, 25, "2359440", "verified"),
        ("g1-medium1", 4, 12, 75, "4946400", "verified"),
        ("g6.5-small1", 2, 2, 75, "3287160", "verified"),
        ("c5-medium1", 2, 4, 25, "3132720", "verified"),
    ]
    for name, vcpu, ram, disk, price, expected in cases:
        status, detail = verify_bundle(name, vcpu, Decimal(ram), Decimal(disk),
                                       Decimal(price), tier_rates(name), mapping)
        assert status == expected, f"{name}: {detail}"
