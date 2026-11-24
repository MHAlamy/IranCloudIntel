"""KaaS pricing rules: fee thresholds, worker costs, control plane, FX."""
from __future__ import annotations

from decimal import Decimal

from comparison.kaas_pricing import (
    FeeTier,
    KaasTariffs,
    fee_for,
    hamravesh_cost,
    irr_to_toman,
    kubit_cost,
    parse_fee_tier_label,
    sotoon_cost,
    worker_cost,
)
from config.loader import load_benchmarks

D = Decimal


def _hamravesh_tariffs() -> KaasTariffs:
    return KaasTariffs(
        cpu_toman=D("595000"),
        ram_toman=D("290000"),
        storage_toman=D("16500"),
        fee_tiers=(
            FeeTier(0, 200, D("70000000")),
            FeeTier(200, 800, D("140000000")),
            FeeTier(800, 1500, D("220000000")),
            FeeTier(1500, None, D("320000000")),
        ),
    )


def test_hamravesh_v1_legacy_fee_thresholds():
    tiers = _hamravesh_tariffs().fee_tiers
    assert [fee_for(value, tiers) for value in (0, 48, 199)] == [
        D("70000000"), D("70000000"), D("70000000"),
    ]
    assert [fee_for(value, tiers) for value in (200, 799)] == [
        D("140000000"), D("140000000"),
    ]
    assert [fee_for(value, tiers) for value in (800, 1499)] == [
        D("220000000"), D("220000000"),
    ]
    assert [fee_for(value, tiers) for value in (1500, 2048, 5000)] == [
        D("320000000"), D("320000000"), D("320000000"),
    ]


def test_hamravesh_v2_current_self_service_fees():
    fees = load_benchmarks().kaas.management_fees["hamravesh_v2"]
    tiers = tuple(
        FeeTier(
            fee.min_vcpu,
            fees[index + 1].min_vcpu if index + 1 < len(fees) else None,
            fee.fee_toman,
        )
        for index, fee in enumerate(fees)
    )
    assert [fee_for(value, tiers) for value in (0, 199, 200, 799)] == [
        D("30000000"), D("30000000"), D("80000000"), D("80000000"),
    ]
    assert [fee_for(value, tiers) for value in (800, 1499, 1500, 5000)] == [
        D("150000000"), D("150000000"), D("240000000"), D("240000000"),
    ]


def test_kubit_ladder_boundaries():
    tiers = (
        FeeTier(0, 65, D("5510000")),
        FeeTier(65, 200, D("14500000")),
        FeeTier(200, 400, D("23900000")),
        FeeTier(400, 800, D("39500000")),
        FeeTier(800, 2000, D("65200000")),
        FeeTier(2000, 4000, D("107400000")),
        FeeTier(4000, 8000, D("177300000")),
    )
    assert fee_for(64, tiers) == D("5510000")
    assert fee_for(65, tiers) == D("14500000")
    assert fee_for(199, tiers) == D("14500000")
    assert fee_for(200, tiers) == D("23900000")
    assert fee_for(800, tiers) == D("65200000")
    assert fee_for(4000, tiers) == D("177300000")
    assert fee_for(7999, tiers) == D("177300000")
    assert fee_for(8000, tiers) is None


def test_worker_costs_for_one_small_scenario():
    ram = D("96")
    disk = D("480")
    assert worker_cost(48, ram, disk, _hamravesh_tariffs()) == D("64320000")

    kubit = KaasTariffs(
        cpu_toman=D("359500"), ram_toman=D("279510"), storage_toman=D("14900"),
    )
    assert worker_cost(48, ram, disk, kubit) == D("51240960")

    sotoon = KaasTariffs(
        cpu_toman=D("1870000"), ram_toman=D("0"), storage_toman=D("21000"),
    )
    assert worker_cost(48, ram, disk, sotoon) == D("99840000")


def test_control_plane_and_totals():
    ram, disk = D("96"), D("480")
    hamravesh = hamravesh_cost(
        48, ram, disk, _hamravesh_tariffs(), D("25000000")
    )
    assert hamravesh.management_toman == D("70000000")
    assert hamravesh.control_plane_toman == D("25000000")
    assert hamravesh.total_toman == D("159320000")

    kubit = kubit_cost(
        48, ram, disk,
        KaasTariffs(
            cpu_toman=D("359500"), ram_toman=D("279510"),
            storage_toman=D("14900"),
            fee_tiers=(FeeTier(0, 65, D("5510000")),
                       FeeTier(65, 200, D("14500000"))),
        ),
        D("10000000"),
    )
    assert kubit.total_toman == D("75740960")

    sotoon = sotoon_cost(
        48, 6, ram, disk,
        KaasTariffs(
            cpu_toman=D("1870000"), ram_toman=D("0"), storage_toman=D("21000"),
            standard_fee_toman=D("17000000"),
            premium_fee_toman=D("40000000"),
            standard_node_fee_toman=D("3100000"),
            premium_node_fee_toman=D("3900000"),
        ),
        D("0"), 30,
    )
    assert sotoon.management_toman == D("35600000")
    assert sotoon.total_toman == D("135440000")


def test_sotoon_switches_to_premium_at_thirty_nodes():
    tariffs = KaasTariffs(
        cpu_toman=D("1870000"), ram_toman=D("0"), storage_toman=D("21000"),
        standard_fee_toman=D("17000000"),
        premium_fee_toman=D("40000000"),
        standard_node_fee_toman=D("3100000"),
        premium_node_fee_toman=D("3900000"),
    )
    below = sotoon_cost(16, 29, D("32"), D("160"), tariffs, D("0"), 30)
    at = sotoon_cost(16, 30, D("32"), D("160"), tariffs, D("0"), 30)
    assert below.management_toman == D("106900000")  # 17M + 29 × 3.1M
    assert at.management_toman == D("157000000")     # 40M + 30 × 3.9M


def test_sotoon_missing_node_fee_stays_unknown():
    tariffs = KaasTariffs(
        cpu_toman=D("1870000"), ram_toman=D("0"), storage_toman=D("21000"),
        standard_fee_toman=D("17000000"),
        premium_fee_toman=D("40000000"),
    )
    cost = sotoon_cost(48, 6, D("96"), D("480"), tariffs, D("0"), 30)
    assert cost.management_toman is None
    assert cost.total_toman is None


def test_kubit_unknown_total_when_fee_missing():
    kubit = kubit_cost(
        2048, D("4096"), D("20480"),
        KaasTariffs(
            cpu_toman=D("359500"), ram_toman=D("279510"),
            storage_toman=D("14900"),
            fee_tiers=(FeeTier(4000, 8000, D("177300000")),),
        ),
        D("10000000"),
    )
    assert kubit.management_toman is None
    assert kubit.total_toman is None
    assert kubit.worker_toman == D("2186280960")


def test_irr_to_toman_conversion():
    assert irr_to_toman("18700000") == D("1870000")
    assert irr_to_toman(170000000) == D("17000000")


def test_fee_tier_label_parsing():
    assert parse_fee_tier_label("0-200") == (0, 200)
    assert parse_fee_tier_label("1500-") == (1500, None)
    assert parse_fee_tier_label("standard") is None
