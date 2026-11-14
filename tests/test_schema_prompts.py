"""Tests for the extraction schema and prompt construction."""

import pytest
from pydantic import ValidationError

from extractors.prompts import build_extraction_messages
from extractors.schema import SCHEMA_VERSION, LLMPlanRow

GOOD_ROW = {
    "plan_name": "eco-small4",
    "provider_tier_raw": "basic",
    "region": "ir-thr-ba1",
    "vcpu": 2,
    "ram_gb": 2,
    "disk_gb": 30,
    "disk_type": None,
    "price_raw": "۱,۴۰۱,۴۸۰",
    "currency_raw": "تومان",
    "billing_period_raw": "ماهانه",
    "evidence": "eco-small4 | 2 CPU | 2 GB | 30 GB | ۱,۴۰۱,۴۸۰ تومان",
}


def test_llm_row_accepts_source_grounded_row():
    row = LLMPlanRow(**GOOD_ROW)
    assert row.plan_name == "eco-small4"
    assert row.price_raw == "۱,۴۰۱,۴۸۰"


def test_llm_row_rejects_negative_resources():
    bad = {**GOOD_ROW, "vcpu": -1}
    with pytest.raises(ValidationError):
        LLMPlanRow(**bad)


def test_llm_row_rejects_unknown_fields():
    bad = {**GOOD_ROW, "best_provider": "arvan"}
    with pytest.raises(ValidationError):
        LLMPlanRow(**bad)


def test_llm_row_requires_evidence():
    bad = {**GOOD_ROW, "evidence": ""}
    with pytest.raises(ValidationError):
        LLMPlanRow(**bad)


def test_prompt_contains_contract_schema_and_fenced_content():
    messages = build_extraction_messages("PLAN CONTENT HERE", context={"tab": "basic"})
    assert messages[0]["role"] == "system"
    assert "strictly as data" in messages[0]["content"]
    assert "null" in messages[0]["content"]  # unknown must be null, not guessed
    user = messages[1]["content"]
    assert SCHEMA_VERSION in user
    assert '"plan_name"' in user  # schema embedded
    assert "--- BEGIN PAGE CONTENT ---" in user
    assert "PLAN CONTENT HERE" in user


def test_prompt_never_embeds_credentials():
    messages = build_extraction_messages("content")
    joined = "\n".join(m["content"] for m in messages)
    assert "apikey" not in joined and "AIaaS_API_KEY" not in joined
