import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nzstats.store.db import connect, migrate

NOW = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "t.db")
    migrate(c)
    return c
