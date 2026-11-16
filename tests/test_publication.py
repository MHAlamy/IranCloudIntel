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
