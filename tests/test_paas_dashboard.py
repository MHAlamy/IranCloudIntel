"""PaaS dashboard tests: four selections, chart, table and Liara silver notes."""
import json
import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import create_app  # noqa: E402
from collectors.arvan_paas import parse_arvan_paas_rates  # noqa: E402
from collectors.hamravesh_paas import parse_hamravesh_paas_rates  # noqa: E402
from collectors.liara_paas import liara_quotes_from_plans, parse_liara_paas_cards  # noqa: E402
from collectors.paas_pipeline import PaasCollection, rate_quotes, run_paas_collection  # noqa: E402
from config.loader import ProviderConfig, SourceConfig  # noqa: E402
from storage.repository import Repository  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "paas"


def fa(n):
    return f"{n:,}".replace(",", "٬").translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _run(repo, evidence_root, slug, name, source_id, quotes):
    provider = ProviderConfig(
        slug=slug, name=name, official_url=f"https://{slug}.example/",
        sources=[SourceConfig(
            id=source_id, service_type="paas",
            url=f"https://{slug}.example/pricing", collection_method="http",
            region_scope="iran", navigation={},
        )],
    )
    outcome = run_paas_collection(
        provider, provider.sources[0], repo,
        collector=lambda src: PaasCollection(quotes=quotes, cleaned="# fixture\n"),
        evidence_root=evidence_root,
    )
    assert outcome.status == "success", outcome.error


def _seed(repo, evidence_root):
    hamravesh = parse_hamravesh_paas_rates(
        (FIXTURES / "hamravesh_rates.html").read_text(encoding="utf-8")
    )
    arvan = parse_arvan_paas_rates(
        (FIXTURES / "arvan_rates.html").read_text(encoding="utf-8")
    )
    liara_cards = json.loads(
        (FIXTURES / "liara_silver_cards.json").read_text(encoding="utf-8")
    )
    _run(repo, evidence_root, "arvan", "ArvanCloud", "arvan_paas", rate_quotes(
        arvan, provider_tier_raw="payg", region="ir-thr-ba1",
        product_family="paas_calculated", pricing_type="configurable_quote",
        plan_prefix="Arvan",
    ))
    _run(repo, evidence_root, "hamravesh", "Hamravesh", "hamravesh_paas", rate_quotes(
        hamravesh, provider_tier_raw="payg", region="ir-iran",
        product_family="paas_calculated", pricing_type="configurable_quote",
        plan_prefix="Hamravesh",
    ))
    _run(repo, evidence_root, "liara", "Liara", "liara_paas",
         liara_quotes_from_plans(parse_liara_paas_cards(liara_cards)))


@pytest.fixture(scope="module")
def paas_client(tmp_path_factory):
    db = tmp_path_factory.mktemp("paas_dash") / "paas.db"
    evidence = tmp_path_factory.mktemp("paas_evidence")
    repo = Repository(db)
    _seed(repo, evidence)
    repo.close()
    app = create_app(db)
    with TestClient(app) as client:
        yield client


def test_paas_page_renders_four_selections(paas_client):
    text = paas_client.get("/paas").text
    assert "پلتفرم ابری توسعه اپلیکیشن (CNAP)" in text
    assert "مقایسه قیمت" in text
    for label in ("1 vCPU + 2 GB", "4 vCPU + 8 GB", "16 vCPU + 32 GB", "32 vCPU + 64 GB"):
        assert label in text
    assert "نقره‌ای" in text


def test_paas_default_prices_and_basis(paas_client):
    text = paas_client.get("/paas").text
    assert fa(2395440) in text     # Arvan calculated
    assert fa(1505000) in text     # Hamravesh calculated
    assert fa(2950000) in text     # Liara published silver
    assert "محاسبه‌شده" in text and "منتشرشده" in text
    soup = BeautifulSoup(text, "html.parser")
    assert len(soup.select(".table-card tbody tr")) == 3
    assert soup.select_one(".chart-card") is not None


def test_paas_liara_missing_for_32_64(paas_client):
    text = paas_client.get("/paas?size=s4").text
    assert fa(48160000) in text    # Hamravesh
    assert fa(76654080) in text    # Arvan
    assert "لیارا در سطح نقره‌ای پلن" in text
    assert "۳۲ vCPU + ۶۴ GB RAM" in text
    assert "ندارد" in text
    assert fa(28000000) not in text


def test_paas_chart_is_cheapest_first(paas_client):
    soup = BeautifulSoup(paas_client.get("/paas").text, "html.parser")
    providers = [b.get_text(strip=True) for b in soup.select(".chart-card .bar-provider")]
    assert providers == ["Hamravesh", "ArvanCloud", "Liara"]


def test_paas_silver_tier_visible(paas_client):
    text = paas_client.get("/paas").text
    assert "سطح: نقره‌ای" in text
    assert "سطح انتخابی لیارا" in text


def test_paas_invalid_size_falls_back(paas_client):
    assert paas_client.get("/paas?size=nope").text == paas_client.get("/paas").text
