"""End-to-end Object Storage collection tests: fake fetchers and mocked LLM.

No live API calls; no network. Fixtures are sanitized page slices from the
verified 2026-11-15 captures.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.arvan_os_clean import build_os_cleaned_markdown  # noqa: E402
from collectors.arvan_os_rates import (  # noqa: E402
    crosscheck_arvan_os_plans,
    parse_faq_overage,
    parse_os_rates,
)
from collectors.hamravesh_os import build_hamravesh_os_markdown, parse_hamravesh_os_plans  # noqa: E402
from collectors.pipeline import FetchResult, run_os_collection  # noqa: E402
from config.loader import ProviderConfig, SourceConfig  # noqa: E402
from extractors.llm import LLMResponse  # noqa: E402
from storage.repository import Repository  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "object_storage"


def _provider(slug, name, source_id, url, navigation):
    return ProviderConfig(
        slug=slug, name=name, official_url=f"https://{slug}.example/",
        sources=[SourceConfig(
            id=source_id, service_type="object_storage", url=url,
            collection_method="playwright", region_scope="iran", navigation=navigation,
        )],
    )


class FakeLLM:
    def __init__(self, rows):
        self._rows = rows

    def extract_rows(self, messages, max_tokens=8000):
        response = LLMResponse(
            content="", model="mock", finish_reason="stop",
            prompt_tokens=100, completion_tokens=50, reasoning_tokens=0,
        )
        return self._rows, response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def repo(tmp_path):
    repository = Repository(tmp_path / "os.db")
    yield repository
    repository.close()


HAMRAVESHE_HTML = (FIXTURES / "hamravesh_os_matrix.html").read_text(encoding="utf-8")
ARVAN_HTML = (FIXTURES / "arvan_os_page.html").read_text(encoding="utf-8")

ARVAN_LLM_ROWS = [
    {"plan_name": "پایه", "price_raw": "رایگان", "storage_raw": "۵ گیگابایت",
     "traffic_raw": "۲۰ گیگابایت", "requests_raw": "۱۰٬۰۰۰", "evidence": "e1"},
    {"plan_name": "رشد", "price_raw": "۱٬۸۰۰٬۰۰۰ تومان", "currency_raw": "تومان",
     "billing_period_raw": "ماهانه", "storage_raw": "۵۰۰ گیگابایت",
     "traffic_raw": "۲ ترابایت", "requests_raw": "۲۰٬۰۰۰", "evidence": "e2"},
    {"plan_name": "حرفه‌ای", "price_raw": "۱۸٬۰۰۰٬۰۰۰ تومان", "currency_raw": "تومان",
     "billing_period_raw": "ماهانه", "storage_raw": "۵ ترابایت",
     "traffic_raw": "۲۰ ترابایت", "requests_raw": "۵۰٬۰۰۰", "evidence": "e3"},
    {"plan_name": "سازمانی", "price_raw": "ثبت درخواست",
     "unlimited_raw": "فضای ذخیره‌سازی نامحدود ترافیک مصرفی نامحدود تعداد درخواست‌های نامحدود",
     "evidence": "e4"},
]


def test_hamravesh_os_collection_deterministic(repo, tmp_path):
    provider = _provider(
        "hamravesh", "Hamravesh", "hamravesh_object_storage",
        "https://hamravesh.com/pricing?service=object_storage",
        {"click_selector": "li", "ready_marker": "x"},
    )

    def fetcher(source):
        return FetchResult(html=HAMRAVESHE_HTML, http_status=200, final_url=source.url)

    outcome = run_os_collection(
        provider, provider.sources[0], repo,
        fetcher=fetcher, cleaner=build_hamravesh_os_markdown,
        os_plans_parser=parse_hamravesh_os_plans,
        evidence_root=tmp_path,
    )
    assert outcome.status == "success" and outcome.error is None
    assert outcome.observations == 5  # four priced plans + quote-only سازمانی
    assert outcome.prompt_tokens == 0 and outcome.completion_tokens == 0

    rows = {r["plan_name"]: r for r in repo.latest_os_observations()}
    assert Decimal(rows["پایه"]["price_in_toman"]) == 375000
    assert Decimal(rows["رشد"]["storage_included_gb"]) == 500
    assert Decimal(rows["رشد"]["traffic_included_gb"]) == 2048
    assert Decimal(rows["حرفه‌ای"]["storage_included_gb"]) == 5120
    assert rows["سازمانی"]["plan_status"] == "quote_only"
    assert rows["سازمانی"]["price_in_toman"] is None
    # documented overage rates stored on the plan observation
    assert Decimal(rows["پایه"]["overage_storage_toman_gb"]) == 3000
    assert Decimal(rows["پایه"]["overage_traffic_toman_gb"]) == 1200
    assert rows["اختصاصی"]["overage_storage_toman_gb"] is not None


def test_hamravesh_os_skip_unchanged(repo, tmp_path):
    provider = _provider(
        "hamravesh", "Hamravesh", "hamravesh_object_storage",
        "https://hamravesh.com/pricing?service=object_storage", {},
    )

    def fetcher(source):
        return FetchResult(html=HAMRAVESHE_HTML, http_status=200, final_url=source.url)

    first = run_os_collection(
        provider, provider.sources[0], repo,
        fetcher=fetcher, cleaner=build_hamravesh_os_markdown,
        os_plans_parser=parse_hamravesh_os_plans, evidence_root=tmp_path,
    )
    second = run_os_collection(
        provider, provider.sources[0], repo,
        fetcher=fetcher, cleaner=build_hamravesh_os_markdown,
        os_plans_parser=parse_hamravesh_os_plans, evidence_root=tmp_path,
    )
    assert first.status == "success" and not first.skipped
    assert second.status == "success" and second.skipped
    assert second.observations == 0


def test_arvan_os_collection_with_mocked_llm(repo, tmp_path):
    provider = _provider(
        "arvan", "ArvanCloud", "arvan_object_storage",
        "https://www.arvancloud.ir/fa/pricing/cloud-storage",
        {"ready_marker": "مصرف مازاد", "llm_plan_extraction": True},
    )

    def fetcher(source):
        return FetchResult(html=ARVAN_HTML, http_status=200, final_url=source.url)

    def rates_parser(html):
        return parse_os_rates(html) + parse_faq_overage(html)

    outcome = run_os_collection(
        provider, provider.sources[0], repo,
        fetcher=fetcher, cleaner=build_os_cleaned_markdown,
        llm_factory=lambda: FakeLLM(ARVAN_LLM_ROWS),
        os_rates_parser=rates_parser,
        os_crosscheck=crosscheck_arvan_os_plans,
        evidence_root=tmp_path,
    )
    assert outcome.status == "success" and outcome.error is None, outcome.error
    assert outcome.observations == 4
    assert outcome.prompt_tokens == 100 and outcome.completion_tokens == 50
    assert outcome.detail["rates_stored"] > 40  # storage/read/write/traffic/feature/FAQ rows

    rates = repo.latest_os_rates(repo._connection.execute(
        "SELECT id FROM providers WHERE slug='arvan'").fetchone()["id"])
    storage = {r["range_max_gb"]: r for r in rates if r["category"] == "storage"}
    assert Decimal(storage["5120"]["amount_toman"]) == 3600
    faq = [r for r in rates if r["category"] == "faq_overage"]
    assert len(faq) == 2

    rows = {r["plan_name"]: r for r in repo.latest_os_observations()}
    assert Decimal(rows["رشد"]["price_in_toman"]) == 1800000
    assert rows["پایه"]["plan_status"] == "free"
    # verbatim raw values are preserved
    assert rows["رشد"]["price_raw"] == "۱٬۸۰۰٬۰۰۰ تومان"

    # cross-check findings land in the review queue (Arvan's own page is
    # inconsistent about سازمانی request limits: card=unlimited vs matrix=۱۰۰٬۰۰۰)
    evidence_dir = Path(rows["رشد"]["evidence"] and tmp_path)
    review_files = list(tmp_path.glob("**/review_queue.json"))
    assert review_files, "cross-check findings must be written to the review queue"
    entries = json.loads(review_files[0].read_text(encoding="utf-8"))
    assert any(e.get("check") == "requests" and e.get("plan") == "سازمانی" for e in entries)


def test_arvan_os_llm_malformed_row_quarantined(repo, tmp_path):
    provider = _provider(
        "arvan", "ArvanCloud", "arvan_object_storage",
        "https://www.arvancloud.ir/fa/pricing/cloud-storage", {},
    )

    def fetcher(source):
        return FetchResult(html=ARVAN_HTML, http_status=200, final_url=source.url)

    bad_rows = ARVAN_LLM_ROWS + [
        {"plan_name": "ساختگی", "price_raw": "۱ تومان", "storage_raw": "۹۹ گیگابایت",
         "traffic_raw": "۹۹ گیگابایت", "evidence": "invented"},
    ]
    outcome = run_os_collection(
        provider, provider.sources[0], repo,
        fetcher=fetcher, cleaner=build_os_cleaned_markdown,
        llm_factory=lambda: FakeLLM(bad_rows),
        os_crosscheck=crosscheck_arvan_os_plans,
        evidence_root=tmp_path,
    )
    assert outcome.status == "success"
    assert outcome.suspect_rows == 1  # quarantined, not recorded
    names = [r["plan_name"] for r in repo.latest_os_observations()]
    assert "ساختگی" not in names
