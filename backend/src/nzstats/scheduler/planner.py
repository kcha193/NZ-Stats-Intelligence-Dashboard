from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta

from nzstats.clock import to_utc_iso


def releases_needing_ingest(
    conn: sqlite3.Connection, adapters: Mapping[str, object], now: datetime, catch_up_days: int
) -> list[str]:
    """Releases already due (published_at <= now, within the catch-up window) with no vintage."""
    slugs = list(adapters)
    marks = ",".join("?" * len(slugs))
    rows = conn.execute(
        f"SELECT r.release_key FROM release r WHERE r.series_slug IN ({marks})"
        " AND r.published_at <= ? AND r.published_at >= ?"
        " AND NOT EXISTS (SELECT 1 FROM vintage v WHERE v.release_id = r.id)"
        " ORDER BY r.published_at",
        (*slugs, to_utc_iso(now), to_utc_iso(now - timedelta(days=catch_up_days))),
    )
    return [r["release_key"] for r in rows]
