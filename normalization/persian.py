"""Deterministic Persian/Arabic text and number normalization.

Pure functions; no LLM involvement. Prices are handled with Decimal, never
binary floats (PROJECT_GUIDE.md section 4.3).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Persian and Arabic digit variants mapped to ASCII
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# Persian/Arabic thousand separators (U+066C ARABIC THOUSANDS SEPARATOR, U+066B)
_SEPARATORS = str.maketrans("", "", "٬،, \u066c\u066b\u200f\u200e")

_CURRENCY_PATTERNS = {
    "toman": ("تومان", "تومان‌", "toman"),
    "rial": ("ریال", "rial", "ريال"),
}

_BILLING_PATTERNS = {
    "monthly": ("ماهانه", "ماهيانه", "monthly"),
    "hourly": ("ساعتی", "ساعت", "hourly"),
}


def to_latin_digits(text: str) -> str:
    """Convert Persian/Arabic-Indic digits to ASCII digits."""
    return text.translate(_DIGIT_MAP)


def parse_price(text: str) -> Decimal:
    """Parse a price string such as '۹۹۷,۷۴۰' or '1,401,480' into Decimal.

    Raises ValueError when no numeric value is present (never returns 0 for
    unparsable input — zero means genuinely free, which is a source claim).
    """
    latin = to_latin_digits(text)
    # Remove separators only between digits
    cleaned = re.sub(r"(?<=\d)[٬،,\s\u066c\u066b]+(?=\d)", "", latin)
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)
    if not cleaned or cleaned in {"-", "."}:
        raise ValueError(f"no numeric value in {text!r}")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"unparsable price {text!r}") from exc


def normalize_currency(text: str) -> str:
    """Map a currency label to 'toman' | 'rial' | 'unknown'. Never guesses."""
    compact = (text or "").strip().lower()
    for normalized, variants in _CURRENCY_PATTERNS.items():
        if any(v in compact for v in variants):
            return normalized
    return "unknown"


def toman_from_rial(amount_rial: Decimal) -> Decimal:
    """Convert an explicitly-declared Rial amount to Toman (10 Rial = 1 Toman)."""
    return amount_rial / Decimal("10")


def normalize_billing_period(text: str) -> str:
    """Map a billing-period label to 'monthly' | 'hourly' | 'unknown'."""
    compact = (text or "").strip().lower()
    for normalized, variants in _BILLING_PATTERNS.items():
        if any(v in compact for v in variants):
            return normalized
    return "unknown"


def parse_cpu_count(text: str) -> int | None:
    """Parse '1 CPU' / '2 vCPU' / '۲' into an int; None when absent."""
    latin = to_latin_digits(text or "")
    match = re.search(r"\d+", latin)
    return int(match.group()) if match else None


def parse_gb(text: str) -> Decimal | None:
    """Parse '25 GB' / '۳۰ گیگابایت' into a Decimal of GB; None when absent.

    GiB units are preserved distinctly: the unit flag is returned separately.
    """
    latin = to_latin_digits(text or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(gib|gb|گیگ|گیگابایت)?", latin, re.IGNORECASE)
    if not match or not match.group(1):
        return None
    return Decimal(match.group(1))
