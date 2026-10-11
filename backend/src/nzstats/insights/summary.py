from __future__ import annotations

import sqlite3
from collections.abc import Collection

from nzstats.catalog import category_for
from nzstats.clock import to_akl_iso
from nzstats.models import ReleaseSummary
from nzstats.store import repo


def release_summary(
    conn: sqlite3.Connection, row: sqlite3.Row, *, analysable_slugs: Collection[str]
) -> ReleaseSummary:
    info = category_for(row["series_slug"])
    return ReleaseSummary(
        id=row["id"],
        release_key=row["release_key"],
        title=row["title"],
        series_slug=row["series_slug"],
        category=info.category,
        importance=info.importance,
        period_label=row["period_label"],
        published_at=to_akl_iso(row["published_at"]),
        status=row["status"],
        headline=row["headline"],
        page_url=row["page_url"],
        has_analysis=row["series_slug"] in analysable_slugs
        and repo.has_any_vintage(conn, row["id"]),
    )
