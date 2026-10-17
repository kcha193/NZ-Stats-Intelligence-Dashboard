"""Wiring: everything a pipeline run needs, built once per process."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field

from nzstats.adapters.base import Adapter
from nzstats.adapters.ect.adapter import EctAdapter
from nzstats.adapters.migration.adapter import MigrationAdapter
from nzstats.config import Settings
from nzstats.sources.artifacts import ArtifactStore
from nzstats.sources.fetcher import Fetcher, FilePacer, build_client
from nzstats.store.db import connect, migrate


def build_adapters(settings: Settings) -> dict[str, Adapter]:
    migration = MigrationAdapter(settings.country_window_months)
    ect = EctAdapter()
    return {migration.series_slug: migration, ect.series_slug: ect}


@dataclass
class Runtime:
    settings: Settings
    conn: sqlite3.Connection
    fetcher: Fetcher
    artifacts: ArtifactStore
    adapters: Mapping[str, Adapter]
    lock: threading.RLock = field(default_factory=threading.RLock)


def build_runtime(settings: Settings, *, fetcher: Fetcher | None = None) -> Runtime:
    conn = connect(settings.db_path)
    migrate(conn)
    fetcher = fetcher or Fetcher(
        build_client(settings.user_agent),
        min_interval=settings.min_interval_seconds,
        pacer=FilePacer(settings.data_dir / ".request-pace", settings.min_interval_seconds),
    )
    return Runtime(
        settings, conn, fetcher, ArtifactStore(settings.raw_dir), build_adapters(settings)
    )
