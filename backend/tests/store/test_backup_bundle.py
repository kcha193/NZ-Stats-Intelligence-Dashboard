"""Native backup sets: the database and its raw artifacts, complete or not at all, and restorable."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nzstats.cli import main
from nzstats.ops.backups import scan_backups
from nzstats.store.backup_bundle import (
    BackupError,
    create_bundle,
    quick_problems,
    restore_bundle,
    verify_bundle,
)
from nzstats.store.backup_check import verify_backup
from nzstats.store.db import connect, migrate

NOW = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)


def make_data(root: Path, n: int = 3):
    """A migrated database whose `raw_artifact` rows point at real content-addressed files under raw/."""
    conn = connect(root / "nzstats.db")
    migrate(conn)
    raw = root / "raw"
    for i in range(n):
        body = f"official file {i}\n".encode() * 50
        sha = hashlib.sha256(body).hexdigest()
        (raw / sha[:2]).mkdir(parents=True, exist_ok=True)
        (raw / sha[:2] / sha).write_bytes(body)
        conn.execute(
            "INSERT INTO raw_artifact(url, sha256, fetched_at, http_status, content_type, size_bytes, path)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                f"https://example.test/{i}",
                sha,
                "2026-10-29T00:00:00Z",
                200,
                "text/csv",
                len(body),
                f"{sha[:2]}/{sha}",
            ),
        )
    return conn, raw


@pytest.fixture()
def data(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    conn, raw = make_data(root)
    yield conn, raw, tmp_path / "backups"
    conn.close()


def tree(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def bundle(data, name="nzstats-2026-10-30-0300"):
    conn, raw, backups = data
    return create_bundle(conn, raw, backups / name, now=NOW), backups / name


# --- creating ---------------------------------------------------------------------------------------------------


def test_a_bundle_holds_the_database_every_raw_artifact_and_a_manifest(data) -> None:
    report, path = bundle(data)
    assert report.ok and report.raw_artifacts == 3 and report.verified_at == "2026-10-30T03:00:00Z"
    assert sorted(p.name for p in path.iterdir()) == ["MANIFEST.json", "nzstats.db", "raw"]
    manifest = json.loads((path / "MANIFEST.json").read_text())
    assert manifest["raw"]["count"] == 3 and manifest["verified"]["ok"] is True
    assert verify_bundle(path).ok and quick_problems(path) == []


def test_only_referenced_artifacts_are_copied_and_stray_files_are_not(data) -> None:
    conn, raw, backups = data
    (raw / "zz").mkdir()
    (raw / "zz" / ".abc.tmp").write_bytes(b"leftover temp file")
    path = backups / "set"
    create_bundle(conn, raw, path, now=NOW)
    assert not (path / "raw" / "zz").exists()


def test_creating_a_bundle_never_changes_the_live_data(data, tmp_path) -> None:
    conn, raw, backups = data
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = tree(raw), hashlib.sha256((tmp_path / "data" / "nzstats.db").read_bytes()).hexdigest()
    create_bundle(conn, raw, backups / "set", now=NOW)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert (
        tree(raw),
        hashlib.sha256((tmp_path / "data" / "nzstats.db").read_bytes()).hexdigest(),
    ) == before


def test_a_missing_raw_artifact_aborts_the_backup_and_leaves_nothing(data) -> None:
    conn, raw, backups = data
    victim = next(p for p in raw.rglob("*") if p.is_file())
    victim.unlink()
    with pytest.raises(BackupError, match="1 referenced raw artifact"):
        create_bundle(conn, raw, backups / "set", now=NOW)
    assert list(backups.iterdir()) == []  # neither the set nor a partial directory


def test_a_damaged_source_artifact_aborts_the_backup(data) -> None:
    conn, raw, backups = data
    victim = next(p for p in raw.rglob("*") if p.is_file())
    victim.write_bytes(victim.read_bytes()[:-1] + b"X")
    with pytest.raises(BackupError, match="1 damaged"):
        create_bundle(conn, raw, backups / "set", now=NOW)
    assert list(backups.iterdir()) == []


def test_an_existing_backup_is_never_overwritten(data) -> None:
    _, path = bundle(data)
    before = tree(path)
    with pytest.raises(BackupError, match="never overwritten"):
        bundle(data)
    assert tree(path) == before


def test_a_path_that_escapes_the_raw_store_is_treated_as_missing(data) -> None:
    conn, raw, backups = data
    conn.execute("UPDATE raw_artifact SET path='../nzstats.db' WHERE id=1")
    with pytest.raises(BackupError, match="missing"):
        create_bundle(conn, raw, backups / "set", now=NOW)


# --- verifying: corrupted and incomplete sets ------------------------------------------------------------------------


def test_a_flipped_byte_in_a_raw_artifact_is_detected(data) -> None:
    _, path = bundle(data)
    victim = next((path / "raw").rglob("*.*"), None) or next(
        p for p in (path / "raw").rglob("*") if p.is_file()
    )
    victim.write_bytes(victim.read_bytes()[:-1] + b"X")
    report = verify_bundle(path)
    assert not report.ok and any("does not match its checksum" in p for p in report.problems)


def test_a_corrupted_database_file_is_detected(data) -> None:
    _, path = bundle(data)
    db = path / "nzstats.db"
    raw = bytearray(db.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    db.write_bytes(bytes(raw))
    report = verify_bundle(path)
    assert (
        not report.ok
        and "the database file does not match its recorded checksum" in report.problems
    )


def test_a_missing_raw_artifact_in_the_set_is_detected(data) -> None:
    _, path = bundle(data)
    next(p for p in (path / "raw").rglob("*") if p.is_file()).unlink()
    assert any("is missing" in p for p in verify_bundle(path).problems)
    assert any("raw artifact(s) are missing" in p for p in quick_problems(path))


def test_an_incomplete_copy_without_its_manifest_is_not_a_backup(data) -> None:
    _, path = bundle(data)
    (path / "MANIFEST.json").unlink()
    assert verify_bundle(path).problems and "manifest is missing" in verify_bundle(path).problems[0]


def test_a_half_copied_set_is_incomplete(data, tmp_path) -> None:
    _, path = bundle(data)
    half = tmp_path / "half"
    shutil.copytree(path, half)
    shutil.rmtree(half / "raw")
    assert not verify_bundle(half).ok and quick_problems(half)


def test_a_database_missing_from_the_set_is_reported(data) -> None:
    _, path = bundle(data)
    (path / "nzstats.db").unlink()
    assert "the database file is missing" in verify_bundle(path).problems


def test_a_malformed_manifest_does_not_crash_verification(data) -> None:
    _, path = bundle(data)
    (path / "MANIFEST.json").write_text(json.dumps({"format": 1, "database": {}}))
    assert "the manifest is malformed" in verify_bundle(path).problems


def test_files_that_are_not_in_the_manifest_are_reported(data) -> None:
    _, path = bundle(data)
    (path / "raw" / "zz").mkdir()
    (path / "raw" / "zz" / "intruder").write_bytes(b"x")
    (path / "notes.txt").write_text("hi")
    problems = verify_bundle(path).problems
    assert "unlisted file raw/zz/intruder" in problems and "unexpected entry notes.txt" in problems


def test_a_manifest_naming_a_path_outside_the_store_is_refused(data) -> None:
    _, path = bundle(data)
    manifest = json.loads((path / "MANIFEST.json").read_text())
    manifest["raw"]["files"][0]["path"] = "../../etc/passwd"
    (path / "MANIFEST.json").write_text(json.dumps(manifest))
    assert any("unsafe raw artifact name" in p for p in verify_bundle(path).problems)


# --- restoring ----------------------------------------------------------------------------------------------------


def test_restore_rebuilds_a_working_data_directory(data, tmp_path) -> None:
    conn, _, _ = data
    _, path = bundle(data)
    before = tree(path)
    restored = tmp_path / "restored"
    report = restore_bundle(path, restored)
    assert report.ok and tree(path) == before  # the bundle itself is only read
    copy = connect(restored / "nzstats.db")
    assert copy.execute("SELECT COUNT(*) FROM raw_artifact").fetchone()[0] == 3
    assert all(
        (restored / "raw" / r[0]).is_file() for r in copy.execute("SELECT path FROM raw_artifact")
    )
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    copy.close()


def test_restore_refuses_a_directory_that_already_has_content(data, tmp_path) -> None:
    _, path = bundle(data)
    target = tmp_path / "live"
    target.mkdir()
    (target / "nzstats.db").write_bytes(b"production")
    with pytest.raises(BackupError, match="not empty"):
        restore_bundle(path, target)
    assert (target / "nzstats.db").read_bytes() == b"production"


def test_restore_refuses_a_corrupt_set_and_creates_nothing(data, tmp_path) -> None:
    _, path = bundle(data)
    next(p for p in (path / "raw").rglob("*") if p.is_file()).unlink()
    with pytest.raises(BackupError, match="failed verification"):
        restore_bundle(path, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_an_older_schema_set_restores_and_asks_for_a_migrate(tmp_path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    conn, raw = make_data(root)
    conn.execute("DELETE FROM schema_version WHERE version>=11")
    for table in ("refresh_run", "ops_process", "ops_job", "ops_alert", "ops_notification"):
        conn.execute(f"DROP TABLE {table}")
    report = create_bundle(conn, raw, tmp_path / "old-set", now=NOW)
    assert report.ok and report.needs_migration and report.schema_version == 10
    restore_bundle(tmp_path / "old-set", tmp_path / "restored")
    copy = connect(tmp_path / "restored" / "nzstats.db")
    assert (
        copy.execute(
            "SELECT name FROM sqlite_master WHERE name='research_summary_no_delete'"
        ).fetchone()
        is not None
    )
    assert migrate(copy) == 12
    copy.close()
    assert verify_backup(tmp_path / "restored" / "nzstats.db").ok


def legacy_data(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    conn, raw = make_data(root)
    conn.execute("DELETE FROM schema_version WHERE version>=11")
    for table in ("refresh_run", "ops_process", "ops_job", "ops_alert", "ops_notification"):
        conn.execute(f"DROP TABLE {table}")
    return conn, raw


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("TRIGGER", "research_summary_no_delete"),
        ("INDEX", "research_summary_version"),
        ("TABLE", "research_summary_review"),
    ],
)
def test_legacy_bundle_creation_rejects_missing_historical_objects(tmp_path, kind, name) -> None:
    conn, raw = legacy_data(tmp_path)
    conn.execute(f"DROP {kind} {name}")
    try:
        with pytest.raises(BackupError, match=f"missing {kind.lower()} {name}"):
            create_bundle(conn, raw, tmp_path / "set", now=NOW)
        assert not (tmp_path / "set").exists()
        assert not list(tmp_path.glob(".set.partial-*"))
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("TRIGGER", "research_summary_no_delete"),
        ("INDEX", "research_summary_version"),
        ("TABLE", "research_summary_review"),
    ],
)
def test_legacy_verification_and_restore_reject_missing_historical_objects(
    tmp_path, kind, name
) -> None:
    conn, raw = legacy_data(tmp_path)
    source = tmp_path / "set"
    create_bundle(conn, raw, source, now=NOW)
    conn.close()
    db = source / "nzstats.db"
    copy = sqlite3.connect(db)
    copy.execute(f"DROP {kind} {name}")
    copy.commit()
    copy.close()
    # Make the checksum consistent: this regression is about schema validation, not hashing.
    manifest = json.loads((source / "MANIFEST.json").read_text())
    manifest["database"].update(
        sha256=hashlib.sha256(db.read_bytes()).hexdigest(), bytes=db.stat().st_size
    )
    (source / "MANIFEST.json").write_text(json.dumps(manifest))
    before = tree(source)
    report = verify_bundle(source)
    assert not report.ok
    assert f"missing {kind.lower()} {name}" in report.problems
    target = tmp_path / "restored"
    target.mkdir()
    (target / "keep.txt").write_text("untouched")
    destination_before = tree(target)
    with pytest.raises(BackupError, match="failed verification"):
        restore_bundle(source, target)
    assert tree(source) == before and tree(target) == destination_before
    with pytest.raises(BackupError, match="failed verification"):
        restore_bundle(source, tmp_path / "new-target")
    assert not (tmp_path / "new-target").exists()


def test_legacy_restore_checks_the_copied_database_and_cleans_up(tmp_path, monkeypatch) -> None:
    conn, raw = legacy_data(tmp_path)
    source = tmp_path / "set"
    create_bundle(conn, raw, source, now=NOW)
    conn.close()
    before = tree(source)
    real_copy = shutil.copyfile

    def damaged_copy(src, dest, **kwargs):
        result = real_copy(src, dest, **kwargs)
        if Path(dest).name == "nzstats.db":
            copy = sqlite3.connect(dest)
            copy.execute("DROP TRIGGER research_summary_no_delete")
            copy.commit()
            copy.close()
        return result

    monkeypatch.setattr(shutil, "copyfile", damaged_copy)
    target = tmp_path / "restored"
    with pytest.raises(BackupError, match="restored copy failed verification"):
        restore_bundle(source, target)
    assert list(target.iterdir()) == []
    assert tree(source) == before


# --- the command line ------------------------------------------------------------------------------------------------


def test_cli_backup_verify_and_restore_round_trip(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "data"
    root.mkdir()
    conn, _ = make_data(root)
    conn.close()
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(root))
    dest = tmp_path / "set"
    assert main(["backup", "--bundle", str(dest)]) == 0
    assert "3 raw artifact(s)" in capsys.readouterr().out
    assert main(["verify-backup", str(dest)]) == 0
    assert main(["restore-backup", str(dest), str(tmp_path / "back")]) == 0
    assert main(["backup", "--bundle", str(dest)]) == 1  # never overwrites
    next(p for p in (dest / "raw").rglob("*") if p.is_file()).unlink()
    capsys.readouterr()
    assert main(["verify-backup", str(dest)]) == 1
    assert "problem: raw artifact" in capsys.readouterr().out
    assert main(["restore-backup", str(dest), str(tmp_path / "back2")]) == 1


def test_the_plain_file_backup_is_unchanged(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "data"
    root.mkdir()
    conn, _ = make_data(root)
    conn.close()
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(root))
    assert main(["backup", str(tmp_path / "plain.db")]) == 0
    assert (
        "and verified" in capsys.readouterr().out
        and main(["verify-backup", str(tmp_path / "plain.db")]) == 0
    )


# --- what the health check sees -----------------------------------------------------------------------------------------


def test_scan_reports_age_and_soundness(data, tmp_path) -> None:
    _, path = bundle(data)
    info = scan_backups(path.parent, NOW + timedelta(hours=5))
    assert (info.state, info.latest.kind, info.latest.verification, info.latest.raw_artifacts) == (
        "ok",
        "bundle",
        "verified",
        3,
    )
    assert info.latest.age_hours == 5.0


def test_scan_calls_an_old_backup_stale_and_an_empty_directory_none(data, tmp_path) -> None:
    _, path = bundle(data)
    assert scan_backups(path.parent, NOW + timedelta(days=8)).state == "stale"
    assert scan_backups(tmp_path / "empty", NOW).state == "none"


def test_scan_flags_a_newest_set_that_is_incomplete_but_keeps_the_last_good_one(data) -> None:
    conn, raw, backups = data
    create_bundle(conn, raw, backups / "nzstats-2026-10-29-0300", now=NOW - timedelta(days=1))
    create_bundle(conn, raw, backups / "nzstats-2026-10-30-0300", now=NOW)
    next(
        p for p in (backups / "nzstats-2026-10-30-0300" / "raw").rglob("*") if p.is_file()
    ).unlink()
    info = scan_backups(backups, NOW + timedelta(hours=1))
    assert info.state == "failed" and info.latest.verification == "incomplete"
    assert info.latest_good.name == "nzstats-2026-10-29-0300"


def _staging(path: Path, when: datetime) -> None:
    path.mkdir()
    os.utime(path, (when.timestamp(), when.timestamp()))


def test_an_unfinished_staging_directory_newer_than_the_last_good_backup_is_a_failed_attempt(
    data,
) -> None:
    _, path = bundle(data)
    _staging(path.parent / ".nzstats-2026-10-30-0400.partial-123", NOW + timedelta(minutes=30))
    assert scan_backups(path.parent, NOW + timedelta(hours=1)).state == "failed"


def test_an_old_leftover_does_not_mask_a_newer_good_backup(data) -> None:
    _, path = bundle(data)
    _staging(path.parent / ".nzstats-2026-10-29-0400.partial-123", NOW - timedelta(days=1))
    assert scan_backups(path.parent, NOW + timedelta(hours=1)).state == "ok"


def test_scan_accepts_plain_file_backups_as_unverified(tmp_path) -> None:
    (tmp_path / "b").mkdir()
    sqlite3.connect(tmp_path / "b" / "old.db").close()
    info = scan_backups(tmp_path / "b", datetime.now(UTC) + timedelta(hours=1))
    assert (info.state, info.latest.kind, info.latest.verification) == ("ok", "file", "unverified")


def test_scan_counts_an_earlier_manual_backup_directory_as_a_database_only_backup(tmp_path) -> None:
    old = tmp_path / "phase-4e-20261029T074530Z"
    old.mkdir()
    (old / "nzstats.db").write_bytes(b"x")
    stamp = (NOW - timedelta(hours=20)).timestamp()
    os.utime(old / "nzstats.db", (stamp, stamp))
    info = scan_backups(tmp_path, NOW)
    assert (info.state, info.latest.kind, info.latest.verification, info.latest.age_hours) == (
        "ok",
        "file",
        "unverified",
        20.0,
    )


def test_one_malformed_manifest_does_not_blind_the_scan(data) -> None:
    _, path = bundle(data)
    bad = path.parent / "nzstats-2026-10-31-0300"
    bad.mkdir()
    (bad / "MANIFEST.json").write_text(
        json.dumps({"format": 1, "created_at": "garbage", "raw": 7, "verified": []})
    )
    info = scan_backups(path.parent, NOW + timedelta(hours=1))
    assert info.entries_seen == 2 and info.latest_good.name == path.name
    assert (
        next(e for e in (info.latest, info.latest_good) if e.name == bad.name).verification
        == "incomplete"
    )


def test_a_backup_in_progress_is_not_a_failed_backup(data) -> None:
    _, path = bundle(data)
    staging = path.parent / ".nzstats-2026-10-30-0400.partial-123"
    _staging(staging, NOW + timedelta(minutes=50))
    assert scan_backups(path.parent, NOW + timedelta(hours=1)).state == "ok"
    os.utime(staging, (NOW.timestamp(), NOW.timestamp()))
    assert (
        scan_backups(path.parent, NOW + timedelta(hours=2)).state == "failed"
    )  # abandoned long ago
