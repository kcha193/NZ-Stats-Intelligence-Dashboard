"""`nzstats status`: read-only, offline, scheduler-free, with exit codes an operator's script can rely on."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from nzstats.cli import main
from nzstats.store.db import connect
from tests.ops import support as S


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): digest(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix != ".lock"
    }


@pytest.fixture()
def world(db_path, clock, monkeypatch):
    """A healthy production-like data directory, with a recent backup, evaluated at the test clock."""
    data = db_path.parent
    conn = connect(db_path)
    S.healthy_world(conn, clock.now)
    backups = data / "backups"
    backups.mkdir()
    source, target = sqlite3.connect(db_path), sqlite3.connect(backups / "nzstats-test.db")
    source.backup(target)
    source.close(), target.close()
    conn.close()
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(data))
    monkeypatch.setattr("nzstats.ops.collect.utc_now", lambda: clock.now)
    return data


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(["status", *argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_ok_exits_zero_and_prints_a_readable_report(world, capsys) -> None:
    code, out, _ = run(capsys)
    assert code == 0 and "operational status: OK" in out
    assert "Collection     enabled" in out and "Freshness" in out and "Issues" not in out


def test_attention_and_critical_have_distinct_exit_codes(world, clock, capsys) -> None:
    conn = connect(world / "nzstats.db")
    S.add_release(conn, "x-2026-10", S.SLUGS[0], clock.now - timedelta(hours=9), ref="2026-10")
    code, out, _ = run(capsys)
    assert code == 1 and "[ATTENTION]" in out and "->" in out
    S.add_release(conn, "y-2026-10", S.SLUGS[1], clock.now - timedelta(days=9), ref="2026-10")
    assert run(capsys)[0] == 2


def test_json_report_is_complete_and_parseable(world, capsys) -> None:
    code, out, _ = run(capsys, "--json")
    report = json.loads(out)
    assert code == 0 and report["overall"] == "ok"
    assert {
        "process",
        "collection",
        "calendar",
        "next_release",
        "freshness",
        "backup",
        "alert_delivery",
        "issues",
    } <= set(report)
    assert report["generated_at"].endswith("+13:00")  # Auckland time, explicit offset


def test_status_changes_nothing_on_disk_even_beside_a_live_writer(world, capsys) -> None:
    """A running dashboard holds the database open with data still in the WAL. `status` must leave both files as they are."""
    writer = connect(world / "nzstats.db")
    writer.execute(
        "UPDATE source_health SET detail='written after the last checkpoint' WHERE source='calendar_ics'"
    )
    main_file, wal = world / "nzstats.db", world / "nzstats.db-wal"
    assert wal.stat().st_size > 0
    before = (digest(main_file), digest(wal), tree(world / "backups"))
    for argv in ((), ("--json",), ("--deep",)):
        run(capsys, *argv)
    assert (digest(main_file), digest(wal), tree(world / "backups")) == before
    detail = writer.execute(
        "SELECT detail FROM source_health WHERE source='calendar_ics'"
    ).fetchone()[0]
    assert detail == "written after the last checkpoint"
    writer.close()


def test_status_does_not_start_the_scheduler(world, capsys, monkeypatch) -> None:
    def boom(*a, **kw):
        raise AssertionError("the scheduler must not be built by `status`")

    monkeypatch.setattr("nzstats.scheduler.jobs.build_scheduler", boom)
    monkeypatch.setattr("nzstats.runtime.build_runtime", boom)
    assert run(capsys)[0] == 0


def test_a_missing_database_is_critical_and_is_not_created(tmp_path, monkeypatch, capsys) -> None:
    data = tmp_path / "nowhere"
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(data))
    code, out, _ = run(capsys)
    assert code == 2 and "database:unreadable" in run(capsys, "--json")[1]
    assert not data.exists()


def test_a_file_that_is_not_a_database_is_critical(tmp_path, monkeypatch, capsys) -> None:
    (tmp_path / "nzstats.db").write_bytes(b"this is not sqlite" * 500)
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path))
    code, out, _ = run(capsys, "--json")
    assert code == 2 and json.loads(out)["issues"][0]["key"] == "database:unreadable"
    assert "this is not sqlite" not in out


def test_a_database_behind_the_code_is_read_not_migrated(
    tmp_path, clock, monkeypatch, capsys
) -> None:
    path = tmp_path / "nzstats.db"
    conn = connect(path)
    from nzstats.store.db import migrate

    migrate(conn)
    conn.execute("DELETE FROM schema_version WHERE version=11")
    for t in ("ops_process", "ops_job", "ops_alert", "ops_notification"):
        conn.execute(f"DROP TABLE {t}")
    conn.close()
    monkeypatch.setenv("NZSTATS_DATA_DIR", str(tmp_path))
    code, out, _ = run(capsys, "--json")
    version = sqlite3.connect(path).execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 10 and "database:schema_behind" in out and code == 1


def test_deep_check_flags_a_damaged_database(world, capsys) -> None:
    path = world / "nzstats.db"
    sqlite3.connect(path).execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw = bytearray(path.read_bytes())
    for page in range(2, len(raw) // 4096):
        raw[page * 4096 : page * 4096 + 64] = b"\xff" * 64
    path.write_bytes(bytes(raw))
    code, out, _ = run(capsys, "--deep", "--json")
    assert code == 2 and {i["key"] for i in json.loads(out)["issues"]} & {
        "database:integrity",
        "database:unreadable",
    }


def test_a_failure_to_compute_is_exit_three_not_a_false_ok(world, capsys, monkeypatch) -> None:
    def broken(*a, **kw):
        raise RuntimeError("bug")

    monkeypatch.setattr("nzstats.ops.collect.collect_status", broken)
    code, _, err = run(capsys)
    assert code == 3 and "could not be computed" in err
