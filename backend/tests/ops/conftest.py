"""Shared fixtures for the operational-health tests: a migrated database and a clock the test moves by hand."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nzstats.store.db import connect, migrate

T0 = datetime(2026, 10, 30, 3, 0, tzinfo=UTC)  # 16:00 NZDT, Fri 30 Oct 2026


class Clock:
    """A wall clock and a monotonic clock that tests advance independently (sleep moves only the wall clock)."""

    def __init__(self, start: datetime = T0) -> None:
        self.now = start
        self.mono = 1000.0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw: float) -> None:
        delta = timedelta(**kw)
        self.now += delta
        self.mono += delta.total_seconds()

    def sleep(self, **kw: float) -> None:
        """The host suspends: wall time passes, the monotonic clock does not."""
        self.now += timedelta(**kw)


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "nzstats.db"
    conn = connect(path)
    migrate(conn)
    conn.close()
    return path


@pytest.fixture()
def conn(db_path: Path):
    c = connect(db_path)
    yield c
    c.close()


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    """Operational monitoring must never leave the machine: any non-loopback lookup or connection fails the test."""
    import socket

    loopback = {"127.0.0.1", "::1", "localhost", None}
    real_connect, real_lookup = socket.socket.connect, socket.getaddrinfo

    def connect(self, address, *a, **kw):
        host = address[0] if isinstance(address, tuple) else None
        if self.family != socket.AF_UNIX and host not in loopback:
            raise AssertionError(f"unexpected network connection to {address!r}")
        return real_connect(self, address, *a, **kw)

    def lookup(host, *a, **kw):
        if host not in loopback:
            raise AssertionError(f"unexpected DNS lookup of {host!r}")
        return real_lookup(host, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", lookup)


@pytest.fixture(autouse=True)
def synthetic_pids_are_alive(monkeypatch):
    """Scenario rows carry made-up pids. Tests that need a dead process pass their own probe."""
    monkeypatch.setattr("nzstats.ops.recorder.pid_alive", lambda pid: True)
