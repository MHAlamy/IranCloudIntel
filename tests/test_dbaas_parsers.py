"""DBaaS deterministic parsers, reference matching and offline import."""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.arvan_dbaas import arvan_dbaas_quotes, parse_arvan_dbaas_rates  # noqa: E402
from collectors.hamravesh_dbaas import (  # noqa: E402
    hamravesh_dbaas_quotes,
    parse_hamravesh_dbaas_rates,
)
from collectors.liara_dbaas import liara_dbaas_quotes_from_plans  # noqa: E402
from collectors.liara_paas import parse_liara_paas_cards  # noqa: E402
from collectors.sotoon_offline import build_dbaas_collection  # noqa: E402
from config.loader import load_benchmarks  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dbaas"
ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "datasets" / "offline" / "sotoon-price-1405-v3"


def test_arvan_dbaas_rates_and_classes():
    rates = parse_arvan_dbaas_rates(
        (FIXTURES / "arvan_rates.html").read_text(encoding="utf-8")
    )
    assert rates["cpu"]["premium"] == Decimal("1292760")
    assert rates["ram"]["premium"] == Decimal("1006510")
    assert rates["storage"]["local"] == Decimal("50400")
    assert rates["cpu"]["standard"] == Decimal("819000")
    assert rates["storage"]["ssd"] == Decimal("36000")

    quotes = arvan_dbaas_quotes(rates)
    assert len(quotes) == 8
    by_key = {
        (q.infra_class, q.vcpu, str(q.ram_gb), str(q.disk_gb)): q for q in quotes
    }
    assert by_key[("local", 1, "2", "20")].price_toman == Decimal("4313780")
    assert by_key[("shared", 1, "2", "20")].price_toman == Decimal("2814300")
    assert by_key[("local", 2, "4", "40")].price_toman == Decimal("8627560")
    assert by_key[("shared", 2, "4", "40")].price_toman == Decimal("5628600")
    assert by_key[("local", 8, "16", "160")].price_toman == Decimal("34510240")
    assert by_key[("shared", 8, "16", "160")].price_toman == Decimal("22514400")
    assert by_key[("local", 1, "2", "20")].product_family == "dbaas_local_calculated"
    assert by_key[("shared", 1, "2", "20")].product_family == "dbaas_shared_calculated"


def test_hamravesh_dbaas_uses_managed_monthly_rates():
    rates = parse_hamravesh_dbaas_rates(
        (FIXTURES / "hamravesh_rates.html").read_text(encoding="utf-8")
    )
    assert rates == {
        "cpu": Decimal("1490000"),
        "ram": Decimal("725000"),
        "storage": Decimal("25000"),
    }

    quotes = hamravesh_dbaas_quotes(rates)
    assert [q.price_toman for q in quotes] == [
        Decimal("3440000"), Decimal("6880000"),
        Decimal("13760000"), Decimal("27520000"),
    ]
    assert all(q.infra_class == "local" for q in quotes)
    assert all(q.disk_type == "SSD" for q in quotes)
    assert all("محلی بودن دیسک تأیید نشده" in " ".join(q.notes) for q in quotes)


def test_liara_dbaas_silver_plans_match_all_reference_sizes():
    cards = json.loads(
        (ROOT / "tests" / "fixtures" / "paas" / "liara_silver_cards.json")
        .read_text(encoding="utf-8")
    )
    quotes = liara_dbaas_quotes_from_plans(parse_liara_paas_cards(cards))
    assert [(q.vcpu, q.ram_gb, q.disk_gb, q.price_toman) for q in quotes] == [
        (1, Decimal("2"), Decimal("20"), Decimal("2950000")),
        (2, Decimal("4"), Decimal("40"), Decimal("5300000")),
        (4, Decimal("8"), Decimal("80"), Decimal("9200000")),
        (8, Decimal("16"), Decimal("160"), Decimal("16000000")),
    ]
    assert all(q.basis == "published" for q in quotes)
    assert all(q.product_family == "dbaas_shared_published" for q in quotes)


def test_sotoon_dbaas_scales_the_published_unit_to_every_reference_size():
    collection = build_dbaas_collection(
        PACKAGE,
        region="Neda",
        local_disk_sku="local_disk",
        network_disk_sku="mana_2_premium",
        sizes=load_benchmarks().dbaas.sizes,
    )
    assert [(p.product_family, p.vcpu, str(p.ram_gb), p.price_toman) for p in collection.plans] == [
        ("dbaas_local_calculated", 1, "2", Decimal("4500000")),
        ("dbaas_shared_calculated", 1, "2", Decimal("3300000")),
        ("dbaas_local_calculated", 2, "4", Decimal("9000000")),
        ("dbaas_shared_calculated", 2, "4", Decimal("6600000")),
        ("dbaas_local_calculated", 4, "8", Decimal("18000000")),
        ("dbaas_shared_calculated", 4, "8", Decimal("13200000")),
        ("dbaas_local_calculated", 8, "16", Decimal("36000000")),
        ("dbaas_shared_calculated", 8, "16", Decimal("26400000")),
    ]
    assert collection.valid_until == "2027-03-20"
    assert all("p.9" in p.evidence for p in collection.plans)
    assert all("Neda" in p.evidence for p in collection.plans)
    assert {p.disk_type for p in collection.plans} == {
        "دیسک محلی", "دیسک مانا نوع ۲ (پرمیوم)"
    }
    medium = next(p for p in collection.plans if p.vcpu == 2 and p.product_family == "dbaas_local_calculated")
    assert "× 2" in medium.evidence
