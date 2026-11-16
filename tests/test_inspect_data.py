import sqlite3

import pytest

from scripts.inspect_data import inspect


def test_inspection_is_bounded_and_does_not_modify_database(tmp_path):
    db = tmp_path / 'legacy.db'
    with sqlite3.connect(db) as conn:
        conn.executescript('''
            CREATE TABLE providers(id INTEGER, slug TEXT);
            CREATE TABLE sources(provider_id INTEGER, service_type TEXT, url TEXT);
            INSERT INTO providers VALUES (1,'a'),(2,'b');
            INSERT INTO sources VALUES (1,'vm','a'),(2,'object_storage','b');
        ''')
    before = db.read_bytes()
    assert inspect(db, 'providers', limit=1) == [dict(slug='a', service_type='vm', url='a')]
    assert db.read_bytes() == before
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='schema_version'").fetchone() is None


def test_missing_database_is_not_created(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(sqlite3.OperationalError):
        inspect(path, 'summary')
    assert not path.exists()


@pytest.mark.parametrize('limit', [0,1001])
def test_invalid_limits_are_rejected_before_opening_db(tmp_path, limit):
    with pytest.raises(ValueError, match='limit'):
        inspect(tmp_path / 'missing.db', 'summary', limit)
