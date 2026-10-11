import sqlite3

from nzstats.cli import main


def test_migrate_then_backup_produces_valid_copy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["migrate"]) == 0
    dest = tmp_path / "backup.db"
    assert main(["backup", str(dest)]) == 0
    tables = {
        r[0]
        for r in sqlite3.connect(dest).execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"release", "observation", "vintage"} <= tables


def test_health_prints_json(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    assert main(["health"]) == 0
    assert '"sources"' in capsys.readouterr().out
