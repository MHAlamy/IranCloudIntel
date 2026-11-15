"""Dashboard tests: routes render Persian comparison views from a seeded DB.

The seeded app fixture (`client_tuple`) lives in conftest.py so that
test_kubit.py can share the same seeded view.
"""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_health(client_tuple):
    client = client_tuple[0]
    assert client.get("/health").json() == {"status": "ok"}


def test_root_redirects_to_vm(client_tuple):
    client = client_tuple[0]
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (301, 302, 307)
    assert response.headers["location"].endswith("/vm")


def test_vm_default_view_is_persian(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm")
    assert response.status_code == 200
    text = response.text
    assert "مقایسه قیمت سرور ابری" in text
    assert "استاندارد" in text  # default tier active
    assert "تومان" in text
    assert "منتشرشده" in text


def test_vm_small_standard_shows_calculated_baseline_only(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm?tier=standard&size=small")
    text = response.text
    # baseline 1/2/20 has no exact bundle (g3-small1 is 1/2/75) -> calculated only
    expected = 234000 + 327600 + 2 * 255060 + 20 * 18000  # 1,431,720
    fa = f"{expected:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert fa in text
    assert "محاسبه\u200cشده" in text
    assert "g3-small1" not in text and "g4-small1" not in text  # near-miss bundles dropped


def test_vm_no_verification_badges_or_region_column(client_tuple):
    client = client_tuple[0]
    text = client.get("/vm").text
    assert "تأیید" not in text  # verification belongs to the plan detail page
    assert "منطقه" not in text  # region column removed; Iran-only noted in header
    assert "تنها برای مناطق ایران" in text


def test_vm_date_only_last_checked(client_tuple):
    client = client_tuple[0]
    text = client.get("/vm").text
    assert "۱۳:۳۰" not in text  # no time-of-day in the table


def test_vm_medium_shows_calculated_price_for_economy(client_tuple):
    client = client_tuple[0]
    # economy has no Medium bundle; rates enable a calculated price
    response = client.get("/vm?tier=economy&size=medium")
    text = response.text
    assert "محاسبه\u200cشده" in text
    expected = 234000 + Decimal("0.7") * (4 * 252000 + 8 * 196200) + 80 * 18000  # 3,478,320
    fa = f"{int(expected):,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    assert fa in text
    # no near-miss approximate bundles for providers with a rate table
    assert "g1-medium1" not in text


def test_vm_pending_providers_visible(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm")
    text = response.text
    for name in ("Liara", "ParsPack", "Cloud.ir"):
        assert name in text
    assert "هنوز گردآوری نشده" in text


def test_vm_foreign_region_plans_hidden_by_default(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm?tier=economy&size=medium")
    assert "c1-medium2" not in response.text  # eu-west plan excluded by Iran scope


def test_vm_calculated_discount_note_only_on_economy(client_tuple):
    """The 30% eco-discount assumption note tracks Arvan's factor only;
    ParsPack's separate 5% monthly-discount note may legitimately appear."""
    client, _ = client_tuple
    arvan_economy = client.get("/vm?tier=economy&size=medium").text
    arvan_standard = client.get("/vm?tier=standard&size=medium").text
    arvan_premium = client.get("/vm?tier=premium&size=medium").text
    assert "تخفیف ۳۰٪" in arvan_economy        # Arvan economy factor 0.7
    assert "تخفیف ۳۰٪" not in arvan_standard   # factor 1.0
    assert "تخفیف ۳۰٪" not in arvan_premium    # factor 1.0

    # Kubit uses full published rates (factor 1.0) even in economy tier
    kubit_economy = client.get("/vm?tier=economy&size=small").text
    kubit_section = kubit_economy.split("Kubit", 1)[-1]
    assert "تخفیف" not in kubit_section


def test_parspack_rows_present_with_adjustment_note(client_tuple):
    client, _ = client_tuple
    fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    standard = client.get("/vm?tier=standard&size=medium").text
    # Medium quote is an exact baseline config -> published basis + adjustment note
    assert "ParsPack" in standard
    assert fa(3408120) in standard  # 3,408,120 monthly (incl. IPv4, 5% discount)
    assert "شامل" in standard and "تخفیف خرید ماهانه" in standard
    # Small: near-miss quote (1/2/25) -> تقریبی with the same note
    small = client.get("/vm?tier=standard&size=small").text
    assert fa(1227300) in small  # 1,227,300


def test_plan_detail_shows_history_and_verification(client_tuple):
    client, g3_offering = client_tuple
    response = client.get(f"/plan/{g3_offering}")
    assert response.status_code == 200
    assert "تاریخچه قیمت" in response.text
    assert "g3-small1" in response.text


def test_status_page_lists_sources_and_runs(client_tuple):
    client = client_tuple[0]
    response = client.get("/status")
    assert response.status_code == 200
    assert "ArvanCloud" in response.text
    assert "موفق" in response.text or "هنوز اجرایی ثبت نشده" in response.text
