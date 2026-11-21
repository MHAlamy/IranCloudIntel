"""Tests for the one-shot collector CLI."""
import collectors.cli as cli


def test_unknown_source_is_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DATA_DIR", tmp_path)
    code = cli.main(["--db", str(tmp_path / "empty.db"), "--source", "no_such_source"])
    assert code == 1
    assert "no enabled source" in capsys.readouterr().out
