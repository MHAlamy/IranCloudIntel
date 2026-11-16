"""Paas deterministic parsers: Hamravesh/Arvan rates and Liara silver cards."""
import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.arvan_paas import parse_arvan_paas_rates  # noqa: E402
from collectors.hamravesh_paas import parse_hamravesh_paas_rates  # noqa: E402
from collectors.liara_paas import liara_quotes_from_plans, parse_liara_paas_cards  # noqa: E402
from collectors.paas_pipeline import rate_quotes  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "paas"


def test_hamravesh_iran_rates_use_first_datacenter():
    html = (FIXTURES / "hamravesh_rates.html").read_text(encoding="utf-8")
    rates = parse_hamravesh_paas_rates(html)
    assert rates == {
        "cpu": Decimal("595000"),
        "ram": Decimal("290000"),
        "storage": Decimal("16500"),
    }


def test_arvan_payg_rates_exclude_ephemeral_storage():
    html = (FIXTURES / "arvan_rates.html").read_text(encoding="utf-8")
    rates = parse_arvan_paas_rates(html)
    assert rates == {
        "cpu": Decimal("655200"),
        "ram": Decimal("510120"),
        "storage": Decimal("36000"),
    }


def test_calculated_quotes_match_reference_selections():
    hamravesh = parse_hamravesh_paas_rates(
        (FIXTURES / "hamravesh_rates.html").read_text(encoding="utf-8")
    )
    arvan = parse_arvan_paas_rates(
        (FIXTURES / "arvan_rates.html").read_text(encoding="utf-8")
    )
    hamravesh_quotes = rate_quotes(
        hamravesh, provider_tier_raw="payg", region="ir-iran",
        product_family="paas_calculated", pricing_type="configurable_quote",
        plan_prefix="Hamravesh",
    )
    arvan_quotes = rate_quotes(
        arvan, provider_tier_raw="payg", region="ir-thr-ba1",
        product_family="paas_calculated", pricing_type="configurable_quote",
        plan_prefix="Arvan",
    )
    assert [(q.vcpu, q.ram_gb, q.disk_gb) for q in hamravesh_quotes] == [
        (1, Decimal("2"), Decimal("20")),
        (4, Decimal("8"), Decimal("80")),
        (16, Decimal("32"), Decimal("320")),
        (32, Decimal("64"), Decimal("640")),
    ]
    assert [q.price_toman for q in hamravesh_quotes] == [
        Decimal("1505000"), Decimal("6020000"),
        Decimal("24080000"), Decimal("48160000"),
    ]
    assert [q.price_toman for q in arvan_quotes] == [
        Decimal("2395440"), Decimal("9581760"),
        Decimal("38327040"), Decimal("76654080"),
    ]


def test_liara_silver_cards_and_reference_mapping():
    cards = json.loads((FIXTURES / "liara_silver_cards.json").read_text(encoding="utf-8"))
    plans = parse_liara_paas_cards(cards)
    assert [p.plan_name for p in plans] == [
        "زمین", "مریخ", "مشتری", "زحل", "اورانوس", "نپتون", "پلوتون"
    ]
    assert (plans[2].vcpu, plans[2].ram_gb, plans[2].disk_gb) == (
        Decimal("1"), Decimal("2"), Decimal("20")
    )
    assert plans[2].monthly_toman == Decimal("2950000")

    quotes = liara_quotes_from_plans(plans)
    assert [(q.vcpu, q.ram_gb, q.disk_gb, q.price_toman) for q in quotes] == [
        (1, Decimal("2"), Decimal("20"), Decimal("2950000")),
        (4, Decimal("8"), Decimal("80"), Decimal("9200000")),
        (16, Decimal("32"), Decimal("320"), Decimal("28000000")),
    ]
    assert all(q.provider_tier_raw == "نقره‌ای" for q in quotes)
    assert all(q.product_family == "paas_fixed" for q in quotes)
