from decimal import Decimal

import pytest

from comparison.tariffs import tier_cost as _tier_cost
from extractors.schema import LLMPlanRow
from normalization.validate import normalize_llm_row


@pytest.mark.parametrize('currency,raw,expected', [('Toman','100','73000'), ('rial','100','7300')])
def test_hourly_monthly_equivalent_preserves_original(currency, raw, expected):
    row = LLMPlanRow(plan_name='test', provider_tier_raw='basic', vcpu=1,
                     ram_gb=2, disk_gb=20, price_raw=raw, currency_raw=currency,
                     billing_period_raw='hourly', evidence='fixture')
    result = normalize_llm_row(row)
    assert result.billing_period == 'monthly'
    assert result.price_in_toman == Decimal(expected)
    assert result.price_value == Decimal(raw)
    assert row.billing_period_raw == 'hourly'
    assert normalize_llm_row(row, monthly_hours=720).price_in_toman == Decimal(expected) / 730 * 720
    unknown = normalize_llm_row(row.model_copy(update={'billing_period_raw':'unknown'}))
    assert unknown.price_in_toman is None and unknown.validation_status == 'suspect'


def tier(lo, hi, amount='2', free=False):
    return dict(range_min_gb=str(lo), range_max_gb=str(hi) if hi is not None else None,
                amount=amount, is_free=free)


@pytest.mark.parametrize('rows', [
    [tier(100,200)], [tier(0,10),tier(20,None)],
    [tier(0,100),tier(50,None)], [tier(0,0)],
    [tier(0,None,'-1')], [tier(0,None,None)],
])
def test_invalid_tariff_is_unknown(rows):
    assert _tier_cost(rows, Decimal(50)) == (None, False)


def test_progressive_tariff_boundaries_and_free_quota():
    rows = [tier(0,5,free=True),tier(5,10,'2'),tier(10,None,'1')]
    for usage, cost in [(0,0),(5,0),(10,10),(15,15)]:
        assert _tier_cost(rows,Decimal(usage)) == (Decimal(cost),True)
