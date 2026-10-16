from __future__ import annotations

import fcntl
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@contextmanager
def _schema_lock(path: Path | str) -> Iterator[None]:
    """Serialise initialisation across processes, including executescript's implicit commits.

    Lock a stable sidecar inode rather than the database, whose locks belong to SQLite. Empty and
    in-memory paths have no shared database file. flock is supported on our POSIX deployment targets.
    """
    if not str(path) or str(path) == ":memory:":
        yield
        return
    target = Path(path).resolve()
    with target.with_name(target.name + ".schema-lock").open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def connect(path: Path | str) -> sqlite3.Connection:
    """Autocommit connection (transactions are explicit via `transaction`)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _schema_lock(path):
        conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
        except BaseException:
            conn.close()
            raise
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    path = next(r[2] for r in conn.execute("PRAGMA database_list") if r[1] == "main")
    with _schema_lock(path):
        return _migrate_locked(conn)


def _migrate_locked(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.name.split("_", 1)[0])
        if version in applied:
            continue
        # One transaction for the script and its marker: a crash or a failing statement must not leave
        # a half-applied schema that the next start cannot re-run. (`executescript` commits whatever
        # is pending first, so the transaction has to be opened inside the script itself.)
        try:
            conn.executescript(
                "BEGIN IMMEDIATE;\n"
                + sql_file.read_text(encoding="utf-8")
                + f"\nINSERT INTO schema_version(version) VALUES ({version});\nCOMMIT;"
            )
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
