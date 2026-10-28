"""Phase 3E: a backup is only a backup once it is shown to restore. The check reads the copy and never writes it."""

import sqlite3

import pytest

from nzstats.cli import main
from nzstats.store.backup_check import verify_backup
from nzstats.store.db import connect, migrate


def _db(tmp_path, name="live.db"):
    conn = connect(tmp_path / name)
    migrate(conn)
    conn.execute(
        "INSERT INTO release(release_key, series_slug, title, published_at, status, first_seen_at, updated_at)"
        " VALUES ('k','s','t','2026-01-01T00:00:00Z','published','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
    )
    return conn


def _copy(conn, dest):
    out = sqlite3.connect(dest)
    conn.backup(out)
    out.close()
    return dest


def test_a_fresh_copy_passes_and_matches_the_live_row_counts(tmp_path):
    live = _db(tmp_path)
    copy = _copy(live, tmp_path / "copy.db")
    report = verify_backup(copy, live=tmp_path / "live.db")
    assert report.ok, report.problems
    assert report.schema_version == report.expected_schema_version >= 8
    assert report.counts["release"] == 1
    assert report.count_differences == {}


def test_the_check_does_not_modify_the_backup(tmp_path):
    copy = _copy(_db(tmp_path), tmp_path / "copy.db")
    before = copy.read_bytes()
    verify_backup(copy)
    assert copy.read_bytes() == before
    assert not (tmp_path / "copy.db-wal").exists()


def test_a_copy_missing_an_append_only_trigger_fails(tmp_path):
    copy = _copy(_db(tmp_path), tmp_path / "copy.db")
    raw = sqlite3.connect(copy)
    raw.execute("DROP TRIGGER research_publication_immutable")
    raw.commit()
    raw.close()
    report = verify_backup(copy)
    assert not report.ok
    assert any("research_publication_immutable" in p for p in report.problems)


def test_an_older_schema_fails(tmp_path):
    copy = _copy(_db(tmp_path), tmp_path / "copy.db")
    raw = sqlite3.connect(copy)
    raw.execute(
        "DELETE FROM schema_version WHERE version = (SELECT MAX(version) FROM schema_version)"
    )
    raw.commit()
    raw.close()
    assert any("schema version" in p for p in verify_backup(copy).problems)


def test_a_corrupt_or_missing_file_fails_without_raising(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database at all" * 100)
    assert not verify_backup(bad).ok
    assert not verify_backup(tmp_path / "missing.db").ok


def test_missing_raw_artifacts_are_reported_when_a_raw_directory_is_given(tmp_path):
    live = _db(tmp_path)
    live.execute("INSERT INTO raw_artifact(url, sha256, fetched_at, http_status, content_type, size_bytes, path)"
                 " VALUES ('https://x.example/a', 'ab', '2026-01-01T00:00:00Z', 200, 'text/html', 3, 'ab/abc')")  # fmt: skip
    copy = _copy(live, tmp_path / "copy.db")
    raw_dir = tmp_path / "raw"
    report = verify_backup(copy, raw_dir=raw_dir)
    assert report.missing_raw == 1 and not report.ok
    (raw_dir / "ab").mkdir(parents=True)
    (raw_dir / "ab" / "abc").write_bytes(b"abc")
    assert verify_backup(copy, raw_dir=raw_dir).ok


def test_row_count_drift_against_the_live_database_is_reported_not_failed(tmp_path):
    live = _db(tmp_path)
    copy = _copy(live, tmp_path / "copy.db")
    live.execute(
        "INSERT INTO release(release_key, series_slug, title, published_at, status, first_seen_at, updated_at)"
        " VALUES ('k2','s','t','2026-01-01T00:00:00Z','published','2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"
    )
    report = verify_backup(copy, live=tmp_path / "live.db")
    assert report.ok and report.count_differences == {"release": (1, 2)}


@pytest.mark.parametrize("extra", [[], ["--raw-dir", "RAW"]])
def test_cli_backup_verifies_its_copy_and_verify_backup_exits_nonzero_on_failure(
    tmp_path, monkeypatch, capsys, extra
):
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path / "data"))
    dest = tmp_path / "b.db"
    assert main(["backup", str(dest)]) == 0
    assert "verified" in capsys.readouterr().out
    args = [a.replace("RAW", str(tmp_path / "data" / "raw")) for a in extra]
    assert main(["verify-backup", str(dest), *args]) == 0
    (tmp_path / "junk.db").write_bytes(b"junk" * 500)
    assert main(["verify-backup", str(tmp_path / "junk.db")]) == 1


def test_a_backup_with_a_wal_sidecar_fails_because_a_restore_would_read_a_different_state(tmp_path):
    copy = _copy(_db(tmp_path), tmp_path / "copy.db")
    (tmp_path / "copy.db-wal").write_bytes(b"x" * 64)
    report = verify_backup(copy)
    assert not report.ok and any("-wal" in p for p in report.problems)


def test_a_missing_live_database_is_a_problem_not_a_crash(tmp_path):
    copy = _copy(_db(tmp_path), tmp_path / "copy.db")
    report = verify_backup(copy, live=tmp_path / "nope.db")
    assert not report.ok and any("live" in p for p in report.problems)
