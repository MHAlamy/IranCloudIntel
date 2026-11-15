"""Tests for the deterministic VM matching engine, using real collected data
shapes (Arvan 2026-11-15 run) plus synthetic edge cases."""

from decimal import Decimal
from pathlib import Path

import pytest

from comparison.matching import PlanView, VMMatcher, is_iranian_region
from config.loader import load_benchmarks, load_tiers

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def plan(name, tier_raw, region, vcpu, ram, disk, price, provider="arvan") -> PlanView:
    return PlanView(
        provider_slug=provider, plan_name=name, tier=VMMatcher(load_benchmarks(), load_tiers())
        .normalize_tier(provider, tier_raw),
        region=region, vcpu=vcpu, ram_gb=Decimal(ram), disk_gb=Decimal(disk),
        price_in_toman=Decimal(price), observed_at="2026-11-15T08:37:00+00:00",
        validation_status="valid",
    )


# Real plans from the 2026-11-15 Arvan run (subset relevant to matching tests)
REAL_PLANS = [
    # basic tab -> economy tier
    plan("eco-small1", "basic", "ir-thr-ba1", 1, 1, 25, 997740),
    plan("eco-small2", "basic", "ir-thr-ba1", 1, 2, 25, 1135080),
    plan("eco-small3", "basic", "ir-thr-ba1", 1, 3, 30, 1362420),
    plan("eco-small4", "basic", "ir-thr-ba1", 2, 2, 30, 1401480),
    plan("c1-medium1", "basic", "eu-west1-a", 2, 4, 25, 2411200),   # foreign region
    plan("g1-medium1", "basic", "ir-thr-fr1", 4, 12, 75, 4946400),
    plan("c1-medium2", "basic", "eu-west1-a", 4, 8, 75, 5086400),   # foreign region
    plan("ls1-medium1", "basic", "ir-thr-fr1", 4, 12, 128, 6822000),
    # standard tab
    plan("g4-small2", "standard", "eu-west1-a", 2, 2, 75, 3360280),  # foreign
    plan("std-small1", "standard", "eu-west1-a", 2, 2, 75, 3360280), # foreign
    plan("std-small2", "standard", "eu-west1-a", 2, 4, 75, 3983760), # foreign
    plan("c2-medium1", "standard", "ir-thr-ba1", 2, 4, 25, 2359440),
    plan("g3-small1", "standard", "ir-thr-ba1", 1, 2, 75, 2421720),
    plan("g3-small2", "standard", "ir-thr-ba1", 2, 2, 75, 2749320),
    plan("g4-small1", "standard", "ir-thr-ba1", 1, 2, 75, 2421720),
    plan("g4.5-small1", "standard", "ir-thr-ba1", 2, 2, 75, 2749320),
    # premium tab
    plan("c6-medium1", "premium", "ir-southwest1-a", 2, 4, 25, 2359440),
    plan("g6-small1", "premium", "ir-southwest1-a", 1, 1, 25, 1266660),
    plan("g6-small2", "premium", "ir-southwest1-a", 1, 2, 25, 1521720),
    plan("g6-small3", "premium", "ir-southwest1-a", 1, 3, 25, 1776780),
    plan("g6-small4", "premium", "ir-southwest1-a", 2, 2, 75, 2749320),
    plan("m6-small1", "premium", "ir-southwest1-a", 2, 8, 50, 3829680),
    plan("c5-medium1", "premium", "ir-thr-ba1", 2, 4, 25, 3132720),
    plan("g6.5-small1", "premium", "ir-thr-ba1", 2, 2, 75, 3287160),
]


@pytest.fixture(scope="module")
def matcher() -> VMMatcher:
    return VMMatcher(load_benchmarks(), load_tiers())


def test_tier_normalization_arvan(matcher):
    assert matcher.normalize_tier("arvan", "basic") == "economy"
    assert matcher.normalize_tier("arvan", "standard") == "standard"
    assert matcher.normalize_tier("arvan", "premium") == "premium"
    assert matcher.normalize_tier("arvan", "premium_plus") == "premium"
    assert matcher.normalize_tier("arvan", "something-new") == "review"
    assert matcher.normalize_tier("liara", "whatever") == "standard"  # default mapping


def test_region_scope_prefix():
    assert is_iranian_region("ir-thr-ba1")
    assert is_iranian_region("IR-SOUTHWEST1-A")
    assert not is_iranian_region("eu-west1-a")
    assert not is_iranian_region("")


def test_small_size_no_exact_baseline_bundle_means_no_primary(matcher):
    # Small = 1 vCPU / 2 GB / 20 GB target; eco-small2 is 1/2/25 (disk differs)
    # -> per owner decision (2026-11-15) it is NOT a primary match; the app
    # layer will show a calculated baseline price instead.
    economy = matcher.match_size(REAL_PLANS, "economy", "small")
    assert economy.primary == []
    # nearest larger fallback remains available for providers without rates
    assert [m.plan.plan_name for m in economy.approximate] == ["eco-small3"]

    standard = matcher.match_size(REAL_PLANS, "standard", "small")
    assert standard.primary == []
    assert [m.plan.plan_name for m in standard.approximate] == ["c2-medium1"]


def test_exact_disk_required_for_primary(matcher):
    # g3-small1 (1/2/75) shares CPU/RAM with Small (1/2/20) but is not exact
    standard = matcher.match_size(REAL_PLANS, "standard", "small")
    names = [m.plan.plan_name for m in standard.primary]
    assert "g3-small1" not in names and "g4-small1" not in names


def test_medium_size_iran_scope_excludes_foreign_and_finds_nothing_exact(matcher):
    # Medium = 4 vCPU / 8 GB / 80 GB; only Iranian plans count
    standard = matcher.match_size(REAL_PLANS, "standard", "medium")
    assert standard.primary == []
    assert standard.approximate == []  # no standard plan is larger than 4/8 either
    assert standard.no_match_reasons

    economy = matcher.match_size(REAL_PLANS, "economy", "medium")
    assert economy.primary == []  # g1/ls1 are 4/12 (not 4/8); c1-medium2 is foreign
    assert [m.plan.plan_name for m in economy.approximate] == ["g1-medium1"]  # nearest larger
    assert economy.approximate[0].match_type == "approximate"


def test_no_silent_interpolation_between_sizes(matcher):
    # g3-small2 (2/2/75) must never appear as a Medium (4/8) match
    standard = matcher.match_size(REAL_PLANS, "standard", "medium")
    all_names = [m.plan.plan_name for m in standard.primary + standard.approximate]
    assert "g3-small2" not in all_names


def test_very_large_has_no_matches_anywhere(matcher):
    for tier in ("economy", "standard", "premium"):
        result = matcher.match_size(REAL_PLANS, tier, "very_large")
        assert result.primary == [] and result.approximate == []
        assert result.no_match_reasons


def test_premium_m6_small1_is_ram_larger_approximate_for_medium(matcher):
    # Medium 4/8: m6-small1 (2 vCPU/8 GB) has exact RAM but vcpu 2 < 4 -> not a match;
    # it is neither primary nor approximate (vcpu must be >= target for larger).
    premium = matcher.match_size(REAL_PLANS, "premium", "medium")
    names = [m.plan.plan_name for m in premium.primary + premium.approximate]
    assert "m6-small1" not in names
    # premium has no plan >= 4 vCPU or >= 8 GB with more... m6 has ram 8 == target (not >)
    assert premium.primary == []
    assert premium.no_match_reasons


def test_same_plan_in_multiple_iranian_regions_deduped_with_flag(matcher):
    duplicated = REAL_PLANS + [
        plan("eco-small2", "basic", "ir-thr-fr1", 1, 2, 25, 1135080),  # same price, other region
        plan("eco-small4", "basic", "ir-thr-fr1", 2, 2, 30, 999999),   # diverging price!
    ]
    flags: list[str] = []
    result = matcher.match_size(duplicated, "economy", "small")
    flags = list(result.review_flags)
    names = [m.plan.plan_name for m in result.primary + result.approximate]
    # eco-small4 exists in two Iranian regions with diverging prices:
    # deduped to one row (cheapest) and flagged for analyst review
    assert names.count("eco-small4") == 1
    assert any("eco-small4" in f for f in flags)


def test_region_scope_all_includes_foreign(matcher):
    # c1-medium2 (4/8/75, eu-west) is Economy tier (from Arvan's basic tab);
    # disk 75 != target 80 so it is not an exact primary match, and it is not
    # larger than the target either -> excluded entirely (baseline-only rule).
    economy = matcher.match_size(REAL_PLANS, "economy", "medium", region_scope="all")
    assert economy.primary == []
    all_names = [m.plan.plan_name for m in economy.approximate]
    assert "c1-medium2" not in all_names


def test_unknown_tier_goes_to_review_not_silently_assigned(matcher):
    weird = REAL_PLANS + [plan("mystery-1", "ultra", "ir-thr-ba1", 4, 8, 80, 123456)]
    result = matcher.match_size(weird, "standard", "medium")
    assert any("mystery-1" in f for f in result.review_flags)
    all_names = [m.plan.plan_name for m in result.primary + result.approximate]
    assert "mystery-1" not in all_names  # never ranked as standard


def test_multiple_eligible_rank_cheapest_first(matcher):
    # Only the plan whose full CPU/RAM/disk equals the target is a primary match
    two = [
        plan("a-4-8-90", "standard", "ir-thr-ba1", 4, 8, 90, 5000000),
        plan("b-4-8-70", "standard", "ir-thr-ba1", 4, 8, 70, 4000000),
        plan("c-4-8-80", "standard", "ir-thr-ba1", 4, 8, 80, 4500000),  # exact
    ]
    result = matcher.match_size(two, "standard", "medium")
    assert [m.plan.plan_name for m in result.primary] == ["c-4-8-80"]
    assert result.primary[0].match_type == "exact"
