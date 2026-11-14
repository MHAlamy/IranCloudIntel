"""Tests for deterministic cleaning of the Arvan pricing panel fixture."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from collectors.arvan_clean import (
    build_cleaned_markdown,
    extract_panel_html,
    parse_plan_rows,
    sha256_text,
)
from normalization.persian import parse_price

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arvan_cloud_server"


@pytest.fixture(scope="module")
def panel_html() -> str:
    return (FIXTURES / "panel_basic.html").read_text(encoding="utf-8")


def test_panel_fixture_yields_eight_rows(panel_html):
    rows = parse_plan_rows(panel_html)
    assert len(rows) == 8


def test_row_fields_match_source(panel_html):
    rows = {r.plan_name: r for r in parse_plan_rows(panel_html)}
    row = rows["eco-small4"]
    assert row.cpu_raw == "2 CPU"
    assert row.ram_raw == "2 GB"
    assert row.disk_raw == "30 GB"
    assert row.price_raw == "۱,۴۰۱,۴۸۰"
    assert row.currency_raw == "تومان"
    assert row.region == "ir-thr-ba1"
    assert row.plan_url and "size=eco-small4" in row.plan_url


def test_regions_differ_within_tab(panel_html):
    rows = parse_plan_rows(panel_html)
    regions = {r.region for r in rows}
    assert {"ir-thr-ba1", "eu-west1-a", "ir-thr-fr1"} <= regions


def test_cleaned_markdown_is_deterministic_and_sanitized(panel_html):
    rows = parse_plan_rows(panel_html)
    url = "https://www.arvancloud.ir/fa/pricing/cloud-server"
    md1 = build_cleaned_markdown("basic", rows, url)
    md2 = build_cleaned_markdown("basic", rows, url)
    assert md1 == md2
    assert sha256_text(md1) == sha256_text(md2)
    # sanitized: no scripts, tags or inline handlers survive
    assert "<script" not in md1 and "onclick" not in md1 and "<svg" not in md1
    # pricing content survived cleaning
    assert "eco-small4" in md1 and "۱,۴۰۱,۴۸۰" in md1 and "تومان" in md1
    assert "c1-medium1" in md1 and "eu-west1-a" in md1


def test_extract_panel_html_requires_known_tab():
    with pytest.raises(ValueError):
        extract_panel_html("<div>x-show='active === basic'</div>", "nonsense")


def test_expected_fixture_matches_source_dump():
    """Guard: the committed expected rows must equal what we parsed and
    manually verified from the live snapshot (parsed_rows_dump.json)."""
    parsed = json.loads((FIXTURES / "parsed_rows_dump.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "expected_basic_rows.json").read_text(encoding="utf-8"))["rows"]
    by_name_parsed = {r["plan_name"]: r for r in parsed}
    assert len(expected) == len(parsed) == 8
    for row in expected:
        src = by_name_parsed[row["plan_name"]]
        assert Decimal(row["price_value"]) == parse_price(src["price_raw"])
        assert row["region"] == src["region"]
        assert row["vcpu"] == int(src["cpu_raw"].split()[0])
        assert float(row["ram_gb"]) == float(src["ram_raw"].split()[0])
        assert float(row["disk_gb"]) == float(src["disk_raw"].split()[0])
