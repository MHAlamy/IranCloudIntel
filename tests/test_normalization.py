"""Tests for deterministic Persian/number/currency normalization."""

from decimal import Decimal

import pytest

from normalization.persian import (
    normalize_billing_period,
    normalize_currency,
    parse_cpu_count,
    parse_gb,
    parse_price,
    to_latin_digits,
    toman_from_rial,
)


def test_persian_digits_convert():
    assert to_latin_digits("۱۴۰۱٬۴۸۰") == "1401٬480"


def test_parse_price_persian_and_latin():
    assert parse_price("۹۹۷,۷۴۰") == Decimal("997740")
    assert parse_price("۱,۴۰۱,۴۸۰") == Decimal("1401480")
    assert parse_price("1,401,480") == Decimal("1401480")
    assert parse_price(" ۲۵۲٬۰۰۰ ") == Decimal("252000")
    assert parse_price("۱٫۵") == Decimal("1.5")


def test_parse_price_rejects_non_numbers():
    for bad in ("", "abc", "-", "—", "تومان"):
        with pytest.raises(ValueError):
            parse_price(bad)


def test_parse_price_zero_is_valid_when_present():
    assert parse_price("۰") == Decimal("0")


def test_currency_recognition():
    assert normalize_currency("تومان") == "toman"
    assert normalize_currency("ریال") == "rial"
    assert normalize_currency("Toman") == "toman"
    assert normalize_currency("dollar") == "unknown"
    assert normalize_currency("") == "unknown"


def test_rial_conversion_explicit_only():
    assert toman_from_rial(Decimal("100000")) == Decimal("10000")
    assert toman_from_rial(Decimal("10")) == Decimal("1")


def test_billing_period_recognition():
    assert normalize_billing_period("ماهانه") == "monthly"
    assert normalize_billing_period("ساعتی") == "hourly"
    assert normalize_billing_period("monthly") == "monthly"
    assert normalize_billing_period("نامشخص") == "unknown"


def test_resource_parsing():
    assert parse_cpu_count("1 CPU") == 1
    assert parse_cpu_count("۴ CPU") == 4
    assert parse_cpu_count("no cpu here") is None
    assert parse_gb("25 GB") == Decimal("25")
    assert parse_gb("۱۲۸ GiB") == Decimal("128")
    assert parse_gb("3.5 GB") == Decimal("3.5")
    assert parse_gb("—") is None
