"""Human-facing date formatting: Jalali (Shamsi) calendar, Tehran time.

Storage uses UTC ISO-8601 internally; every string shown to the dashboard's
Iranian audience is converted here to the Jalali calendar with Persian digits.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import jdatetime

TEHRAN = ZoneInfo("Asia/Tehran")

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def utc_to_tehran(iso_string: str) -> datetime:
    """Parse a UTC ISO-8601 string and convert it to Tehran local time."""
    dt = datetime.fromisoformat(iso_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TEHRAN)


def format_jalali(iso_string: str, with_time: bool = True, persian_digits: bool = True) -> str:
    """Format a stored UTC timestamp as a readable Jalali date(time).

    Example: '2026-11-14T15:41:50+00:00' -> '۱۴۰۵/۰۸/۲۳ ۱۹:۱۱' (Tehran time).
    """
    tehran_dt = utc_to_tehran(iso_string)
    jalali = jdatetime.datetime.fromgregorian(datetime=tehran_dt)
    pattern = "%Y/%m/%d" + (" %H:%M" if with_time else "")
    text = jalali.strftime(pattern)
    return text.translate(_PERSIAN_DIGITS) if persian_digits else text
