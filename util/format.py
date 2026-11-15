"""Human-facing formatting: Persian digits, Toman amounts, Jalali dates."""

from __future__ import annotations

from decimal import Decimal

_PERSIAN = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(text: str) -> str:
    return str(text).translate(_PERSIAN)


def format_toman(value: Decimal | int | str, with_currency: bool = True) -> str:
    """Format a Toman amount with thousand separators and Persian digits."""
    amount = int(Decimal(value))
    grouped = f"{amount:,}"
    text = to_persian_digits(grouped)
    return f"{text} تومان" if with_currency else text


def format_number(value: Decimal | int | float | str) -> str:
    """Format a plain number with Persian digits (for specs like 4 vCPU)."""
    text = str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return to_persian_digits(text)
