from types import SimpleNamespace

import pytest

from storage.repository import Repository


def rate(category='cpu', amount='100'):
    return SimpleNamespace(category=category, region='iran', unit='unit',
                           tier_label='basic', amount_toman=amount, evidence='fixture')


def test_atomic_publication_failure_recheck_and_recovery(tmp_path):
    repo = Repository(tmp_path / 'prices.db')
    reader = Repository(tmp_path / 'prices.db')
    provider = repo.ensure_provider('test', 'Test', 'https://example.test')
    source = repo.ensure_source(provider, 'vm', 'https://example.test/prices', 'http')
    first = repo.start_run(source)
    repo.record_rates(first, provider, [rate(), rate('ram')])
    assert not reader.latest_rates(provider)
    repo.publish_run(first, 'success', content_hash='first')
    assert len(reader.latest_rates(provider)) == 2
    partial = repo.start_run(source)
    repo.record_rates(partial, provider, [rate(amount='999')])
    with pytest.raises(ValueError, match='incomplete'):
        repo.publish_run(partial, 'success', content_hash='partial')
    repo.publish_run(partial, 'failed', error='incomplete')
    assert {r['amount_toman'] for r in reader.latest_rates(provider)} == {'100'}
    assert repo.freshness('vm')[0]['stale']
    retry = repo.start_run(source)
    repo.publish_run(retry, 'success', content_hash='first')
    assert not repo.freshness('vm')[0]['stale']
    assert len(reader.latest_rates(provider)) == 2
    empty = repo.start_run(source)
    with pytest.raises(ValueError, match='empty'):
        repo.publish_run(empty, 'success', content_hash='new')
    repo.publish_run(empty, 'failed', error='empty')
    reader.close()
    repo.close()


def os_rate(category='storage', tier_label='استاندارد',
            range_label='۵ گیگابایت تا ۵ ترابایت', amount_toman='3600'):
    return SimpleNamespace(
        category=category, region='iran', unit='هر گیگابایت',
        tier_label=tier_label, range_label=range_label,
        range_min_gb='5', range_max_gb='5120',
        amount_toman=amount_toman, is_free=False, evidence='fixture',
    )


def test_retired_review_only_os_rates_do_not_block_publication(tmp_path):
    """Dropping a review-only category (Arvan FAQ) is not a partial publication."""
    repo = Repository(tmp_path / 'os_rates.db')
    provider = repo.ensure_provider('arvan', 'ArvanCloud', 'https://www.arvancloud.ir/')
    source = repo.ensure_source(
        provider, 'object_storage',
        'https://www.arvancloud.ir/fa/pricing/cloud-storage', 'playwright',
    )
    first = repo.start_run(source)
    repo.record_os_rates(first, provider, [
        os_rate(),
        os_rate('faq_overage', 'فضای ذخیره‌سازی', 'مصرف مازاد (طبق پرسش‌های رایج)', '1400'),
    ])
    repo.publish_run(first, 'success', content_hash='first')
    second = repo.start_run(source)
    repo.record_os_rates(second, provider, [os_rate()])
    repo.publish_run(second, 'success', content_hash='second')  # must not raise
    repo.close()
