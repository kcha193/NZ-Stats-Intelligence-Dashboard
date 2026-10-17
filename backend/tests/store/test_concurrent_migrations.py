"""F06: simultaneous CLI/server starts apply each migration exactly once."""

import multiprocessing
import sqlite3
import time

import pytest

from nzstats.store.db import MIGRATIONS_DIR, connect


class SlowVersionRead(sqlite3.Connection):
    def execute(self, sql, parameters=()):
        cursor = super().execute(sql, parameters)
        if sql == "SELECT version FROM schema_version":
            # Freeze the observed version set and widen the real race. Correct serialisation keeps
            # other migration callers outside this section until the first caller has committed.
            observed = list(cursor)
            time.sleep(0.1)
            return iter(observed)
        return cursor


def _migrate_worker(path, barrier, results):
    from nzstats.store.db import migrate

    conn = sqlite3.connect(path, factory=SlowVersionRead, isolation_level=None, timeout=10)
    try:
        barrier.wait(timeout=10)
        results.put(migrate(conn))
    except Exception as exc:
        results.put((type(exc).__name__, str(exc)))
    finally:
        conn.close()


@pytest.mark.parametrize("initial_version", [0, 1])
def test_concurrent_creation_and_upgrade_are_idempotent(tmp_path, initial_version):
    path = tmp_path / "concurrent.db"
    conn = connect(path)
    conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    if initial_version:
        conn.executescript((MIGRATIONS_DIR / "001_init.sql").read_text())
        conn.execute("INSERT INTO schema_version VALUES (1)")
        conn.execute("INSERT INTO source_health(source,state) VALUES ('preserved','ok')")
    conn.close()
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(4)
    results = ctx.Queue()
    processes = [
        ctx.Process(target=_migrate_worker, args=(str(path), barrier, results)) for _ in range(4)
    ]
    try:
        for process in processes:
            process.start()
        outcomes = [results.get(timeout=20) for _ in processes]
        assert outcomes == [2, 2, 2, 2]
    finally:
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join()
        results.close()
    conn = connect(path)
    assert [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY version")] == [
        1,
        2,
    ]
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    if initial_version:
        assert (
            conn.execute("SELECT state FROM source_health WHERE source='preserved'").fetchone()[0]
            == "ok"
        )
    conn.close()


def _initialise_worker(path, index, barrier, results):
    from nzstats.store.db import connect, migrate

    try:
        barrier.wait(timeout=10)
        conn = connect(path)
        version = migrate(conn)
        conn.execute("INSERT INTO source_health(source,state) VALUES (?, 'ok')", (str(index),))
        conn.close()
        results.put(version)
    except Exception as exc:
        results.put((type(exc).__name__, str(exc)))


def test_simultaneous_initialisation_retains_committed_rows(tmp_path):
    path = tmp_path / "initialise.db"
    ctx = multiprocessing.get_context("spawn")
    barrier, results = ctx.Barrier(4), ctx.Queue()
    processes = [
        ctx.Process(target=_initialise_worker, args=(str(path), i, barrier, results))
        for i in range(4)
    ]
    try:
        for process in processes:
            process.start()
        assert [results.get(timeout=20) for _ in processes] == [2, 2, 2, 2]
    finally:
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join()
        results.close()
    conn = connect(path)
    assert conn.execute("SELECT COUNT(*) FROM source_health").fetchone()[0] == 4
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()
