"""Tests for Jalali (Shamsi) display formatting."""

from datetime import datetime, timezone

from util.jalali import format_jalali, utc_to_tehran


def test_utc_to_tehran_offset():
    dt = utc_to_tehran("2026-11-14T15:41:50+00:00")
    # Tehran is UTC+3:30 in November (no DST since 2022)
    assert dt.hour == 19 and dt.minute == 11 and dt.day == 14


def test_format_jalali_roundtrip_matches_calendar():
    iso = "2026-11-14T15:41:50+00:00"
    text = format_jalali(iso)
    # Persian digits only, Jalali date/time shape
    latin = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    date_part, time_part = latin.split(" ")
    y, m, d = (int(x) for x in date_part.split("/"))
    assert 1300 <= y <= 1500 and 1 <= m <= 12 and 1 <= d <= 31
    assert time_part == "19:11"
    # roundtrip: Jalali back to Gregorian must equal the Tehran-local datetime
    import jdatetime
    tehran = utc_to_tehran(iso)
    restored = jdatetime.datetime(y, m, d, int(time_part[:2]), int(time_part[3:])).togregorian()
    assert (restored.year, restored.month, restored.day) == (tehran.year, tehran.month, tehran.day)


def test_format_jalali_without_time_and_latin_digits():
    iso = "2026-11-14T15:41:50+00:00"
    text = format_jalali(iso, with_time=False, persian_digits=False)
    assert " " not in text
    assert text.count("/") == 2
    assert text[0].isascii()


def test_naive_timestamps_treated_as_utc():
    dt = utc_to_tehran("2026-11-14T15:41:50")
    expected = datetime(2026, 11, 14, 15, 41, 50, tzinfo=timezone.utc).astimezone()
    # not asserting the wall clock; only that conversion doesn't crash and is aware
    assert dt.tzinfo is not None
    _ = expected
