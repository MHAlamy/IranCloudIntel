"""Tests for the one-shot collector CLI."""
import collectors.cli as cli
import pytest

from util.runlock import RunLock, RunLocked


def test_unknown_source_is_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DATA_DIR", tmp_path)
    code = cli.main(["--db", str(tmp_path / "empty.db"), "--source", "no_such_source"])
    assert code == 1
    assert "no enabled source" in capsys.readouterr().out


def test_environment_database_uses_lock_on_same_disk(tmp_path, monkeypatch):
    db = tmp_path / "mounted" / "history.db"
    monkeypatch.setenv("CLOUD_INTEL_DB", str(db))
    with RunLock(db.parent / ".collection.lock"), pytest.raises(RunLocked):
        cli.main(["--source", "no_such_source"])
    assert not db.exists()
    assert cli.main(["--source", "no_such_source"]) == 1
    assert db.is_file()
