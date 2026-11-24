"""KaaS dashboard: four offerings, six scenarios, charts and explanation box."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402
from collectors.hamravesh_kaas import parse_hamravesh_kaas  # noqa: E402
from collectors.kaas_pipeline import KaasCollection, run_kaas_collection  # noqa: E402
from collectors.kubit_kaas import parse_kubit_kaas  # noqa: E402
from collectors.sotoon_offline import collect_sotoon_kaas_offline  # noqa: E402
from config.loader import load_providers  # noqa: E402
from storage.repository import Repository  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fa(amount: int) -> str:
    return f"{amount:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _provider_and_source(slug: str):
    provider = next(p for p in load_providers().providers if p.slug == slug)
    source = next(s for s in provider.sources if s.service_type == "kaas")
    return provider, source


def _run(repo, evidence_root, slug, collector):
    provider, source = _provider_and_source(slug)
    outcome = run_kaas_collection(
        provider, source, repo, collector=collector, evidence_root=evidence_root,
    )
    assert outcome.status == "success", outcome.error


def _seed(repo, evidence_root):
    hamravesh_html = (FIXTURES / "kaas" / "hamravesh_rates.html").read_text(encoding="utf-8")
    kubit_html = (FIXTURES / "object_storage" / "kubit_pricing.html").read_text(encoding="utf-8")
    _run(
        repo, evidence_root, "hamravesh",
        lambda source: KaasCollection(rates=parse_hamravesh_kaas(hamravesh_html)),
    )
    _run(
        repo, evidence_root, "kubit",
        lambda source: KaasCollection(rates=parse_kubit_kaas(kubit_html)),
    )
    _run(repo, evidence_root, "sotoon", collect_sotoon_kaas_offline)


@pytest.fixture(scope="module")
def kaas_client(tmp_path_factory):
    db = tmp_path_factory.mktemp("kaas_dash") / "kaas.db"
    evidence = tmp_path_factory.mktemp("kaas_evidence")
    repo = Repository(db)
    _seed(repo, evidence)
    repo.close()
    app = create_app(db)
    with TestClient(app) as client:
        yield client


def test_default_scenario_renders_four_offerings(kaas_client):
    text = kaas_client.get("/kaas").text
    assert "کوبرنتیز مدیریت‌شده (KaaS)" in text
    assert "مقایسه قیمت" in text
    for name in ("هم‌روش v1", "هم‌روش v2", "Kubit", "Sotoon"):
        assert name in text
    for amount in (75740960, 119320000, 135440000, 159320000):
        assert fa(amount) in text
    assert "قیمت‌های قدیمی" in text and "قیمت‌های جدید خودسرویس KaaS" in text
    assert "مدیریت = اشتراک + هزینه هر نود" in text
    soup = BeautifulSoup(text, "html.parser")
    assert len(soup.select(".table-card")[0].select("tbody tr")) == 4
    assert len(soup.select(".chart-card")[0].select(".bar-provider")) == 4


def test_chart_is_cheapest_first(kaas_client):
    soup = BeautifulSoup(kaas_client.get("/kaas?scenario=small").text, "html.parser")
    providers = [
        bar.get_text(strip=True)
        for bar in soup.select(".chart-card")[0].select(".bar-provider")
    ]
    assert providers == ["Kubit", "هم‌روش v2", "Sotoon", "هم‌روش v1"]


def test_xxxlarge_uses_legacy_v1_and_current_v2_fees(kaas_client):
    text = kaas_client.get("/kaas?scenario=xxx_large").text
    assert fa(3089320000) in text   # Hamravesh v1 legacy 320M fee
    assert fa(3009320000) in text   # Hamravesh v2 current 240M fee (assumed)
    assert fa(4424640000) in text   # Sotoon premium: 40M + 32 × 3.9M + workers
    assert "تماس بگیرید" in text
    soup = BeautifulSoup(text, "html.parser")
    assert len(soup.select(".table-card")[0].select("tbody tr")) == 4


def test_explanation_box_sits_between_charts_and_tables(kaas_client):
    text = kaas_client.get("/kaas?scenario=medium").text
    assert text.index("chart-card") < text.index("method-card") < text.index("table-card")
    soup = BeautifulSoup(text, "html.parser")
    method = soup.select_one(".method-card")
    assert "نحوه محاسبه قیمت و فرض‌ها" in method.get_text(" ", strip=True)
    assert "P = ۲×CPU + RAM" in method.get_text(" ", strip=True)


def test_all_scenarios_and_fee_only_matrices(kaas_client):
    text = kaas_client.get("/kaas?scenario=small").text
    assert "همه سناریوها — جمع ماهانه" in text
    assert "مقایسه‌ی فقط هزینه مدیریت" in text
    for amount in (14500000, 30000000, 35600000, 70000000):
        assert fa(amount) in text
    soup = BeautifulSoup(text, "html.parser")
    matrix_tables = soup.select(".table-card")
    assert len(matrix_tables) == 3
    for table in matrix_tables[1:]:
        assert len(table.select("thead th")) == 7  # provider + six scenarios
        assert len(table.select("tbody tr")) == 4


def test_invalid_scenario_falls_back(kaas_client):
    assert kaas_client.get("/kaas?scenario=nope").text == kaas_client.get("/kaas").text


def test_placeholders_and_home_link(kaas_client):
    text = kaas_client.get("/kaas").text
    assert "مقایسه قابلیت‌ها" in text and "مقایسه عملکرد" in text
    assert "به‌زودی" in text
    assert 'href="/kaas"' in kaas_client.get("/").text
