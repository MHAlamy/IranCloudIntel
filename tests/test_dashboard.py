"""Dashboard tests: routes render Persian comparison views from a seeded DB.

The seeded app fixture (`client_tuple`) lives in conftest.py so that
test_kubit.py can share the same seeded view.
"""

import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_health(client_tuple):
    client = client_tuple[0]
    assert client.get("/health").json() == {"status": "ok"}


def test_vm_default_view_is_persian(client_tuple):
    client = client_tuple[0]
    response = client.get("/vm")
    assert response.status_code == 200
    text = response.text
    assert "سرور ابری" in text
    assert "مقایسه قیمت" in text
    assert "مقایسه قابلیت‌ها" in text
    assert "مقایسه عملکرد" in text
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
    assert "تأیید" not in text.split('class="price-table"', 1)[-1].split("</table>", 1)[0]  # verification belongs to the plan detail page
    assert "منطقه" not in text  # region column removed; Iran-only noted in header
    assert "تنها برای مناطق ایران" in text


def test_vm_date_only_last_checked(client_tuple):
    client = client_tuple[0]
    text = client.get("/vm").text
    # scope to the table: the freshness panel legitimately shows times
    table = text.split('class="price-table"', 1)[-1].split("</table>", 1)[0]
    assert not re.search(r"[۰-۹]{2}:[۰-۹]{2}", table)  # no time-of-day in the table


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
    # Cloud.ir was removed from scope (owner decision 2026-11-15)
    for name in ("Liara", "ParsPack", "Kubit", "ArvanCloud"):
        assert name in text
    assert "Cloud.ir" not in text


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

    # Kubit uses full published rates (factor 1.0) even in economy tier.
    # Kubit is the last provider in the canonical table order, so splitting on
    # the LAST occurrence scopes the check to its table row (the chart bar
    # appears earlier and other providers' notes follow it).
    kubit_economy = client.get("/vm?tier=economy&size=small").text
    kubit_section = kubit_economy.rsplit("Kubit", 1)[-1]
    assert "تخفیف" not in kubit_section


def test_parspack_rows_present_with_adjustment_note(client_tuple):
    client, _ = client_tuple
    fa = lambda n: f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    # Owner decision 2026-11-15: ParsPack compares under Economy.
    economy = client.get("/vm?tier=economy&size=medium").text
    # Medium quote is an exact baseline config -> published basis + adjustment note
    assert "ParsPack" in economy
    assert fa(3408120) in economy  # 3,408,120 monthly (incl. IPv4, 5% discount)
    assert "شامل" in economy and "تخفیف خرید ماهانه" in economy
    # Small: near-miss quote (1/2/25) -> تقریبی with the same note
    small = client.get("/vm?tier=economy&size=small").text
    assert fa(1227300) in small  # 1,227,300


def test_vm_provider_order_consistent_across_views(client_tuple):
    """Same canonical provider order on every (tier, size) view and the status page."""
    client, _ = client_tuple
    expected = ["ArvanCloud", "Liara", "ParsPack", "Kubit", "Sotoon"]
    orders = []
    for size in ("small", "medium", "large", "very_large"):
        text = client.get(f"/vm?tier=standard&size={size}").text
        # scope to the table: the bar chart above it is intentionally sorted
        # cheapest-first, not in canonical provider order
        table_text = text.split('class="price-table"', 1)[-1]
        positions = [table_text.find(name) for name in expected]
        assert all(pos >= 0 for pos in positions), f"missing provider on {size}"
        assert positions == sorted(positions), f"order broken on {size}"

    # Sotoon has no source row in this seeded database (it is imported from an
    # offline document), so the status page lists only the network providers.
    status = client.get("/status").text
    positions = [status.find(name) for name in expected[:-1]]
    assert positions == sorted(positions)


def test_vm_chart_bars_cheapest_first_and_proportional(client_tuple):
    """The CSS bar chart orders priced providers cheapest-first and scales the
    most expensive price to full width (economy/medium seeded prices:
    ParsPack 3,408,120 < Arvan 3,478,320 < Kubit 3,895,080 < Liara 4,800,000)."""
    client, _ = client_tuple
    text = client.get("/vm?tier=economy&size=medium").text
    assert "مقایسه بصری قیمت‌ها" in text
    # chart section precedes the table, so first name occurrence is the bar row
    positions = [text.find(name) for name in ("ParsPack", "ArvanCloud", "Kubit", "Liara")]
    assert all(p >= 0 for p in positions)
    assert positions == sorted(positions), "bars not ordered cheapest-first"
    assert 'style="width: 100%"' in text  # Liara is the most expensive
    assert "bar-published" in text and "bar-calculated" in text


def test_vm_chart_marks_missing_providers(client_tuple):
    """Providers with no usable price in the selection get an empty dashed
    track and an em-dash price — never a zero-width bar."""
    client, _ = client_tuple
    text = client.get("/vm?tier=standard&size=small").text
    assert "bar-empty" in text  # Liara/ParsPack compare under Economy now
    assert "bar-price-none" in text


def test_vm_chart_absent_when_no_prices_at_all():
    """With no priced rows at all the chart section is omitted entirely."""
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    from app.data import build_vm_view
    from storage.repository import Repository

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db = _Path(tmp) / "empty.db"
        repo = Repository(db)
        try:
            view = build_vm_view(repo, "standard", "medium")
        finally:
            repo.close()
    assert "chart" not in view  # chart section omitted entirely


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
