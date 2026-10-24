"""A seeded data directory shared by the publication tests (real fixture files, never production data)."""

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nzstats.config import load_settings
from nzstats.pipeline.ingest import ingest_release
from nzstats.publish.provenance import FIXTURE_MARKER
from nzstats.runtime import build_runtime
from tests.cpi_support import NOW as CPI_NOW
from tests.cpi_support import seed_cpi
from tests.ect_support import NOW as ECT_NOW
from tests.ect_support import seed_ect
from tests.support import FakeSite, seed_from_fixtures

EXPORT_NOW = datetime(2026, 10, 24, 8, 0, tzinfo=UTC)


def _ingest(data_dir: Path, seeder, months, now) -> None:
    site = FakeSite()
    rt = build_runtime(load_settings({"NZSTATS_DATA_DIR": str(data_dir)}), fetcher=site.fetcher())
    for month in months:
        key = seeder(rt, site, month)[1]
        assert ingest_release(rt, key, now_fn=lambda: now).outcome in ("ingested", "unchanged")
    rt.conn.close()


@pytest.fixture(scope="session")
def full_dir(tmp_path_factory) -> Path:
    """Migration + ECT + CPI, as `scripts/seed_e2e_db.py` builds them."""
    target = tmp_path_factory.mktemp("full")
    seed_from_fixtures(target)
    _ingest(target, seed_ect, ("2026-08", "2026-09"), ECT_NOW)
    _ingest(target, seed_cpi, ("2026-03", "2026-06"), CPI_NOW)
    return target


@pytest.fixture(scope="session")
def migration_only_dir(tmp_path_factory) -> Path:
    target = tmp_path_factory.mktemp("migration-only")
    seed_from_fixtures(target)
    return target


@pytest.fixture()
def snapshot(full_dir, tmp_path) -> Path:
    """A fixture-origin snapshot of `full_dir` in a throwaway directory."""
    from nzstats.publish.snapshot import export_snapshot

    out = tmp_path / "snapshot"
    export_snapshot(full_dir, out, now=EXPORT_NOW, allow_fixtures=True)
    return out


@pytest.fixture()
def copy_of(tmp_path):
    def _copy(src: Path) -> Path:
        dest = tmp_path / "copy"
        shutil.copytree(src, dest)
        return dest

    return _copy


@pytest.fixture()
def production_dir(full_dir, tmp_path) -> Path:
    """The fixture data with its marker removed, standing in for a production data directory."""
    dest = tmp_path / "production"
    shutil.copytree(full_dir, dest)
    (dest / FIXTURE_MARKER).unlink()
    db = sqlite3.connect(dest / "nzstats.db")
    db.execute("PRAGMA user_version = 0")  # the database's own fixture flag, cleared too
    db.close()
    return dest
