from datetime import datetime, timedelta, timezone

import pytest

from collectors.pipeline import run_collection, FetchError
from test_pipeline import make_source, fake_fetcher, arvan_cleaner, mock_llm_factory
from storage.repository import Repository
from util.fingerprint import collection_fingerprint


def test_configuration_and_parser_changes_invalidate_cache(tmp_path):
    config = tmp_path / 'config'
    config.mkdir()
    file = config / 'benchmarks.yaml'
    file.write_text('hours: 730')
    first = collection_fingerprint(root=tmp_path)
    file.write_text('hours: 720')
    second = collection_fingerprint(root=tmp_path)
    assert first != second
    code = tmp_path / 'collectors'
    code.mkdir()
    (code / 'parser.py').write_text('version = 2')
    assert second != collection_fingerprint(root=tmp_path)


@pytest.mark.parametrize('mode', ['empty', 'suspect', 'second_tab_failure'])
def test_bad_extraction_preserves_accepted_prices(tmp_path, mode):
    repo = Repository(tmp_path / 'db.sqlite')
    provider, source = make_source()
    kwargs = dict(provider=provider, source=source, repo=repo,
                  fetcher=fake_fetcher(), cleaner=arvan_cleaner, evidence_root=tmp_path / 'evidence')
    assert run_collection(llm_factory=mock_llm_factory([]), **kwargs).status == 'success'
    before = [(r['id'], r['price_in_toman']) for r in repo.latest_observations()]

    class Broken:
        def __enter__(self):
            self.client = mock_llm_factory([])()
            self.calls = 0
            return self
        def __exit__(self, *args):
            self.client.close()
        def extract_rows(self, messages):
            self.calls += 1
            rows, telemetry = self.client.extract_rows(messages)
            if mode == 'empty':
                rows = []
            elif mode == 'suspect':
                rows = [dict(r, currency_raw='unknown') for r in rows]
            elif self.calls == 2:
                raise FetchError('second tab failed after staged observations')
            return rows, telemetry

    if mode == 'second_tab_failure':
        _, kwargs['source'] = make_source(tabs=('basic','second'))
        def two_tabs(html, url, tabs):
            content = arvan_cleaner(html, url, ('basic',))['basic']
            return {tab: content for tab in tabs}
        kwargs['cleaner'] = two_tabs
    outcome = run_collection(llm_factory=Broken, force=True, **kwargs)
    assert outcome.status == 'failed'
    assert [(r['id'], r['price_in_toman']) for r in repo.latest_observations()] == before
    assert repo.freshness('vm')[0]['stale']
    repo.close()


def test_old_success_is_stale_and_source_config_change_reextracts(tmp_path):
    repo = Repository(tmp_path / 'db.sqlite')
    provider, source = make_source()
    calls = []
    kwargs = dict(provider=provider, source=source, repo=repo,
                  fetcher=fake_fetcher(), cleaner=arvan_cleaner, evidence_root=tmp_path / 'evidence',
                  llm_factory=mock_llm_factory(calls))
    run_collection(**kwargs)
    old = (datetime.now(timezone.utc)-timedelta(hours=49)).isoformat()
    repo._connection.execute('UPDATE collection_runs SET finished_at=?', (old,))
    repo._connection.commit()
    assert repo.freshness('vm')[0]['stale']
    source.navigation['ready_marker'] = 'changed configuration'
    assert not run_collection(**kwargs).skipped
    assert len(calls) == 2
    assert not repo.freshness('vm')[0]['stale']
    repo.close()
