import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nzstats.api.app import create_app
from nzstats.config import load_settings
from nzstats.research.api import research_router
from nzstats.store.db import connect, migrate

from .public_support import registry

NOW = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "t.db")
    migrate(c)
    return c


@pytest.fixture()
def make(tmp_path, monkeypatch):
    monkeypatch.delenv("NZSTATS_PUBLIC_RESEARCH", raising=False)
    settings = load_settings({"NZSTATS_DATA_DIR": str(tmp_path / "data")})

    def build(*, enabled=True, reg=None, routers=None):
        reg = registry() if reg is None else reg
        loader = reg if callable(reg) else (lambda: reg)
        routers = (
            [research_router(enabled=enabled, registry=loader)] if routers is None else routers
        )
        return TestClient(create_app(settings, routers=routers))

    conn = connect(settings.db_path)
    build(enabled=False)  # migrates the database
    return build, conn


# Modules whose scenarios must read identically whether each cell has its own BT..ET or each baseline shares one (Phase 4AG).
ROW_STYLE_MODULES = {
    "test_table_grid",
    "test_table_forecast",
    "test_table_ingest",
    "test_table_view",
    "test_table_reconcile",
    "test_table_store",
    "test_table_e2e",
    "test_table_api",
    "test_table_context",
}


def pytest_generate_tests(metafunc):
    if metafunc.module.__name__.rsplit(".", 1)[-1] in ROW_STYLE_MODULES:
        metafunc.fixturenames.append("pdf_style")
        metafunc.parametrize("pdf_style", ["cell", "row"], indirect=True)


@pytest.fixture()
def pdf_style(request, monkeypatch):
    from . import pdf_table_support

    monkeypatch.setattr(pdf_table_support, "STYLE", request.param)
    return request.param
