"""Raw artifacts under concurrent writers (Phase 3F review P2). Every document body is SYNTHETIC FIXTURE text.

The raw file is content-addressed, so two stores of the same bytes share one path. A store that fails, or that
links no version to its bytes, removes the file it wrote; that must never remove a file another writer is
registering in a transaction this connection cannot see. The invariant checked throughout: after every writer has
finished, each committed version's raw file exists (`purge.integrity_problems`).

Interleavings are forced with events and a pause at the moment the first writer deletes its file, never with sleeps.
Where a pause cannot be reached because the other writer is locked out, the wait times out and the test proceeds:
the outcome checked afterwards does not depend on how long the wait was.
"""

import os
import sqlite3
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from nzstats.research import purge, store
from nzstats.research.manual_import import ImportRefused
from nzstats.sources.artifacts import ArtifactStore
from nzstats.store.db import connect

from .support import BASE
from .test_purge import (
    URL,
    apply,
    count,
    do_import,
    html,
    imported_and_published,
    raw_files,
)

URL_B = f"{BASE}/research/mirror-b"
BACKEND = Path(__file__).resolve().parents[2]
WAIT = 3.0  # how long the first writer waits for the second to reach its registration


@pytest.fixture()
def artifacts(tmp_path):
    return ArtifactStore(tmp_path / "raw")


def db_path(conn) -> str:
    return next(r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main")


def fail_in(monkeypatch, thread_name: str) -> None:
    """Make `add_version` fail for one named thread only (a rolled-back store)."""
    real = store.add_version

    def add_version(*a, **kw):
        if threading.current_thread().name == thread_name:
            raise sqlite3.OperationalError("disk I/O error")
        return real(*a, **kw)

    monkeypatch.setattr(store, "add_version", add_version)


def write_locked_elsewhere(path: str) -> bool:
    """Whether another connection is refused the write lock right now."""
    probe = sqlite3.connect(path, timeout=0, isolation_level=None)
    try:
        probe.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError:
        return True
    else:
        probe.execute("ROLLBACK")
        return False
    finally:
        probe.close()


# --- the reported race --------------------------------------------------------------------------------------------


def test_a_rolled_back_store_does_not_delete_the_file_a_concurrent_store_registers(
    conn, artifacts, monkeypatch
):
    """Writer A fails and rolls back; writer B stored the same bytes and is mid-transaction when A cleans up."""
    path = db_path(conn)
    fail_in(monkeypatch, "writer-a")
    registered, a_done = threading.Event(), threading.Event()
    real_add_version = store.add_version  # already wrapped: B passes through it

    def add_version_b(*a, **kw):
        out = real_add_version(*a, **kw)
        if threading.current_thread().name == "writer-b":
            registered.set()  # B's raw_artifact row is written, uncommitted
            assert a_done.wait(30)
        return out

    monkeypatch.setattr(store, "add_version", add_version_b)
    results: dict = {}

    def writer_b():
        results["b"] = do_import(connect(path), artifacts, url=URL_B)

    b = threading.Thread(target=writer_b, name="writer-b")
    removals = []
    real_remove = artifacts.remove

    def remove(rel):
        removals.append(rel)
        b.start()
        registered.wait(WAIT)  # reachable only if A's cleanup does not exclude other writers
        return real_remove(rel)

    monkeypatch.setattr(artifacts, "remove", remove)
    a = threading.Thread(
        target=lambda: results.update(a=_outcome(conn, artifacts)), name="writer-a"
    )
    a.start()
    a.join(60)
    a_done.set()
    b.join(60)

    assert results["a"] == "OperationalError" and removals, (
        "writer A must have failed and cleaned up"
    )
    assert results["b"].outcome == "new"
    verify = connect(path)
    assert purge.integrity_problems(verify, artifacts) == []
    assert count(verify, "raw_artifact") == 1 and len(raw_files(artifacts)) == 1


def _outcome(conn, artifacts) -> str:
    try:
        do_import(conn, artifacts)
    except sqlite3.OperationalError as exc:
        return type(exc).__name__
    return "stored"


def test_the_same_race_across_two_processes(conn, artifacts, tmp_path, monkeypatch):
    """Writer B is a separate process; it pauses once its row is written and before it commits."""
    path = db_path(conn)
    marker, go = tmp_path / "b-registered", tmp_path / "b-go"
    script = textwrap.dedent(
        """
        import sys, time
        from pathlib import Path
        from nzstats.research import store
        from nzstats.sources.artifacts import ArtifactStore
        from nzstats.store.db import connect
        from tests.research.test_purge import do_import
        db, raw, url, marker, go = sys.argv[1:6]
        real = store.add_version

        def add_version(*a, **kw):
            out = real(*a, **kw)
            Path(marker).write_text("registered")
            deadline = time.monotonic() + 60
            while not Path(go).exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            return out

        store.add_version = add_version
        do_import(connect(db), ArtifactStore(Path(raw)), url=url)
        """
    )
    fail_in(monkeypatch, "writer-a")
    proc: list[subprocess.Popen] = []
    real_remove = artifacts.remove

    def remove(rel):
        proc.append(subprocess.Popen(
            [sys.executable, "-c", script, path, str(artifacts.root), URL_B, str(marker), str(go)],
            cwd=BACKEND, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        ))  # fmt: skip
        deadline = (
            time.monotonic() + 20
        )  # B needs a moment to start; give up early only once A holds the lock
        while (
            not marker.exists()
            and time.monotonic() < deadline
            and write_locked_elsewhere(path) is False
        ):
            time.sleep(0.05)
        return real_remove(rel)

    monkeypatch.setattr(artifacts, "remove", remove)
    a = threading.Thread(target=lambda: _outcome(conn, artifacts), name="writer-a")
    a.start()
    a.join(60)
    go.write_text("go")
    err = proc[0].communicate(timeout=60)[1].decode()
    assert proc[0].returncode == 0, err
    verify = connect(path)
    assert purge.integrity_problems(verify, artifacts) == []
    assert count(verify, "raw_artifact") == 1 and len(raw_files(artifacts)) == 1


# --- cleanup excludes other writers ---------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["rolled_back", "duplicate", "unchanged_manual"])
def test_a_store_removes_its_unlinked_file_only_while_it_holds_the_write_lock(
    conn, artifacts, monkeypatch, case
):
    path = db_path(conn)
    if case == "duplicate":
        do_import(conn, artifacts)
        body, url = html().replace(b"</body>", b"<!-- mirror --></body>"), f"{BASE}/research/mirror"
    elif case == "unchanged_manual":
        do_import(conn, artifacts)
        body, url = html().replace(b"</body>", b"<!-- saved again --></body>"), URL
    else:
        body, url = html(), URL
        monkeypatch.setattr(store, "add_version", _boom)
    seen = []
    real_remove = artifacts.remove

    def remove(rel):
        seen.append(write_locked_elsewhere(path))
        return real_remove(rel)

    monkeypatch.setattr(artifacts, "remove", remove)
    try:
        do_import(conn, artifacts, body, url=url)
    except sqlite3.OperationalError:
        assert case == "rolled_back"
    assert seen == [True]
    assert len(raw_files(artifacts)) == (0 if case == "rolled_back" else 1)
    assert purge.integrity_problems(conn, artifacts) == []


def _boom(*a, **kw):
    raise sqlite3.OperationalError("disk I/O error")


def test_a_failed_import_leaves_no_file_and_does_not_hold_the_lock(conn, artifacts, monkeypatch):
    monkeypatch.setattr(store, "add_version", _boom)
    with pytest.raises(sqlite3.OperationalError):
        do_import(conn, artifacts)
    assert raw_files(artifacts) == [] and count(conn, "raw_artifact") == 0
    assert not write_locked_elsewhere(db_path(conn))


# --- both commit; duplicate and unchanged handling -----------------------------------------------------------------


def test_two_writers_of_identical_bytes_both_commit_and_share_one_file(conn, artifacts):
    path = db_path(conn)
    barrier, errors = threading.Barrier(2), []

    def writer(url):
        try:
            barrier.wait(30)
            do_import(connect(path), artifacts, url=url)
        except Exception as exc:  # noqa: BLE001 - reported by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(u,)) for u in (URL, URL_B)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert errors == []
    # the second store sees the first's text and records a duplicate; either way one file, nothing dangling
    assert count(conn, "research_publication") == 2 and len(raw_files(artifacts)) == 1
    assert purge.integrity_problems(conn, artifacts) == []
    assert purge.find_orphan_files(conn, artifacts, older_than_seconds=0) == []


def test_unchanged_and_duplicate_imports_keep_one_linked_file(conn, artifacts):
    first = do_import(conn, artifacts)
    assert do_import(conn, artifacts).outcome == "unchanged"
    assert do_import(conn, artifacts, url=URL_B).outcome == "duplicate"
    files = raw_files(artifacts)
    assert len(files) == 1 and count(conn, "raw_artifact") == 1 and first.version_id is not None
    assert purge.integrity_problems(conn, artifacts) == []


# --- purge overlapping a store -------------------------------------------------------------------------------------


def test_a_purge_that_commits_after_the_early_check_still_refuses_the_store_and_leaves_no_file(
    conn, artifacts, monkeypatch
):
    imported_and_published(conn, artifacts)
    apply(conn, artifacts)
    assert raw_files(artifacts) == []
    real, calls = store.purged_text, []

    def late(*a, **kw):  # the early check, made before the purge was seen, finds nothing
        calls.append(1)
        return None if len(calls) <= 2 else real(*a, **kw)

    monkeypatch.setattr(store, "purged_text", late)
    with pytest.raises(ImportRefused, match="purged"):
        do_import(conn, artifacts, url=URL_B)
    assert raw_files(artifacts) == [] and count(conn, "raw_artifact") == 0
    assert not write_locked_elsewhere(db_path(conn))


# --- the orphan sweep ----------------------------------------------------------------------------------------------


def stray_file(artifacts) -> Path:
    stray = artifacts.root / "ab" / ("ab" + "0" * 62)
    stray.parent.mkdir(parents=True)
    stray.write_bytes(b"left by a crash")
    old = time.time() - 7200
    os.utime(stray, (old, old))
    return stray


def test_the_sweep_cannot_delete_a_file_a_writer_registers_meanwhile(conn, artifacts):
    """An old unreferenced file with the bytes' name is listed; a store of those bytes starts during the sweep."""
    body = html()
    target = artifacts.root / artifacts.rel_for(body)
    target.parent.mkdir(parents=True)
    target.write_bytes(body)
    old = time.time() - 7200
    os.utime(target, (old, old))
    path, results = db_path(conn), {}
    writer = threading.Thread(
        target=lambda: results.update(r=do_import(connect(path), artifacts, url=URL_B))
    )

    class Spy:
        root = artifacts.root

        def files(self):
            writer.start()
            writer.join(WAIT)  # finishes inside the wait unless the sweep excludes other writers
            return artifacts.files()

    assert purge.remove_orphan_files(conn, Spy(), older_than_seconds=3600) == 1
    writer.join(60)
    assert results["r"].outcome == "new"
    verify = connect(path)
    assert purge.integrity_problems(verify, artifacts) == []
    assert len(raw_files(artifacts)) == 1


def test_the_sweep_lists_and_removes_files_only_while_it_holds_the_write_lock(conn, artifacts):
    stray = stray_file(artifacts)
    path, seen = db_path(conn), []

    class Spy:
        root = artifacts.root

        def files(self):
            seen.append(write_locked_elsewhere(path))
            return artifacts.files()

    assert purge.remove_orphan_files(conn, Spy(), older_than_seconds=3600) == 1
    assert seen == [True] and not stray.exists()
    assert not write_locked_elsewhere(path)
