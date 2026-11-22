"""DBaaS dashboard: two classes, four sizes, chart, missing and manual rows."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402
from collectors.arvan_dbaas import arvan_dbaas_quotes, parse_arvan_dbaas_rates  # noqa: E402
from collectors.dbaas_pipeline import DbaasCollection, run_dbaas_collection  # noqa: E402
from collectors.hamravesh_dbaas import (  # noqa: E402
    hamravesh_dbaas_quotes,
    parse_hamravesh_dbaas_rates,
)
from collectors.liara_dbaas import liara_dbaas_quotes_from_plans  # noqa: E402
from collectors.liara_paas import parse_liara_paas_cards  # noqa: E402
from collectors.offline_pipeline import run_offline_collection  # noqa: E402
from collectors.sotoon_offline import collect_sotoon_dbaas_offline  # noqa: E402
from config.loader import ProviderConfig, SourceConfig, load_providers  # noqa: E402
from storage.repository import Repository  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dbaas"
ROOT = Path(__file__).resolve().parent.parent


def fa(n):
    return f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _run(repo, evidence_root, slug, name, source_id, quotes):
    provider = ProviderConfig(
        slug=slug, name=name, official_url=f"https://{slug}.example/",
        sources=[SourceConfig(
            id=source_id, service_type="dbaas",
            url=f"https://{slug}.example/pricing", collection_method="http",
            region_scope="iran", navigation={},
        )],
    )
    outcome = run_dbaas_collection(
        provider, provider.sources[0], repo,
        collector=lambda src: DbaasCollection(quotes=quotes, cleaned="# fixture\n"),
        evidence_root=evidence_root,
    )
    assert outcome.status == "success", outcome.error


def _seed(repo, evidence_root):
    arvan = parse_arvan_dbaas_rates(
        (FIXTURES / "arvan_rates.html").read_text(encoding="utf-8")
    )
    hamravesh = parse_hamravesh_dbaas_rates(
        (FIXTURES / "hamravesh_rates.html").read_text(encoding="utf-8")
    )
    cards = json.loads(
        (ROOT / "tests" / "fixtures" / "paas" / "liara_silver_cards.json")
        .read_text(encoding="utf-8")
    )
    _run(repo, evidence_root, "arvan", "ArvanCloud", "arvan_dbaas",
         arvan_dbaas_quotes(arvan))
    _run(repo, evidence_root, "hamravesh", "Hamravesh", "hamravesh_dbaas",
         hamravesh_dbaas_quotes(hamravesh))
    _run(repo, evidence_root, "liara", "Liara", "liara_dbaas",
         liara_dbaas_quotes_from_plans(parse_liara_paas_cards(cards)))

    sotoon_provider = next(p for p in load_providers().providers if p.slug == "sotoon")
    sotoon_source = next(
        s for s in sotoon_provider.sources if s.service_type == "dbaas"
    )
    outcome = run_offline_collection(
        sotoon_provider, sotoon_source, repo, collect_sotoon_dbaas_offline,
        evidence_root=evidence_root,
    )
    assert outcome.status == "success", outcome.error


@pytest.fixture(scope="module")
def dbaas_client(tmp_path_factory):
    db = tmp_path_factory.mktemp("dbaas_dash") / "dbaas.db"
    evidence = tmp_path_factory.mktemp("dbaas_evidence")
    repo = Repository(db)
    _seed(repo, evidence)
    repo.close()
    app = create_app(db)
    with TestClient(app) as client:
        yield client


def test_default_class_and_size_render_three_providers(dbaas_client):
    text = dbaas_client.get("/dbaas").text
    assert "دیتابیس ابری (DBaaS)" in text
    assert "مقایسه قیمت" in text
    assert "محلی / پرمیوم (کلاس A)" in text
    for amount in (3440000, 4313780, 4500000):
        assert fa(amount) in text
    assert "منبع دستی: Sotoon price list v3" in text
    soup = BeautifulSoup(text, "html.parser")
    assert len(soup.select(".table-card tbody tr")) == 3
    assert soup.select_one(".chart-card") is not None


def test_shared_class_switches_series_and_basis(dbaas_client):
    text = dbaas_client.get("/dbaas?class=shared&size=small").text
    assert "اشتراکی / شبکه (کلاس B)" in text
    for amount in (2814300, 2950000, 3300000):
        assert fa(amount) in text
    assert "منتشرشده" in text and "محاسبه‌شده" in text
    soup = BeautifulSoup(text, "html.parser")
    providers = [b.get_text(strip=True) for b in soup.select(".chart-card .bar-provider")]
    assert providers == ["ArvanCloud", "Liara", "Sotoon"]


def test_medium_size_includes_stacked_sotoon(dbaas_client):
    text = dbaas_client.get("/dbaas?class=local&size=medium").text
    assert fa(6880000) in text    # Hamravesh
    assert fa(8627560) in text    # Arvan
    assert fa(9000000) in text    # Sotoon: 2 × 1 vCPU + 2 GB bundle + 40 GB local disk
    assert "× تعداد واحد" in text
    soup = BeautifulSoup(text, "html.parser")
    assert len(soup.select(".table-card tbody tr")) == 3

    shared = dbaas_client.get("/dbaas?class=shared&size=medium").text
    assert fa(5300000) in shared  # Liara
    assert fa(5628600) in shared  # Arvan
    assert fa(6600000) in shared  # Sotoon: 2 × shared bundle + 40 GB premium disk


def test_invalid_class_or_size_falls_back(dbaas_client):
    default = dbaas_client.get("/dbaas").text
    assert dbaas_client.get("/dbaas?class=nope&size=nope").text == default


def test_method_card_sits_between_chart_and_table(dbaas_client):
    text = dbaas_client.get("/dbaas?class=local&size=medium").text
    assert text.index("chart-card") < text.index("method-card") < text.index("table-card")
    soup = BeautifulSoup(text, "html.parser")
    method = soup.select_one(".method-card")
    assert method is not None
    assert "نحوه محاسبه قیمت و انتخاب کلاس" in method.get_text(" ", strip=True)
    assert "کلاس A" in method.get_text(" ", strip=True)


def test_placeholders_and_home_link(dbaas_client):
    text = dbaas_client.get("/dbaas").text
    assert "مقایسه قابلیت‌ها" in text and "مقایسه عملکرد" in text
    assert "به‌زودی" in text
    assert 'href="/dbaas"' in dbaas_client.get("/").text
