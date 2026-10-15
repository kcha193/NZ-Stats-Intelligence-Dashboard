from __future__ import annotations

import sqlite3
from collections.abc import Collection
from datetime import datetime

from nzstats.catalog import INACTIVE_CATEGORIES
from nzstats.clock import to_akl_iso, to_utc_iso
from nzstats.insights.migration import SLUG, build_release_analysis
from nzstats.insights.summary import release_summary
from nzstats.models import FeaturedOut, InactiveCategory, Kpi, OverviewOut, SourceHealthOut


def health_rows(conn: sqlite3.Connection) -> list[SourceHealthOut]:
    return [
        SourceHealthOut(
            source=r["source"],
            state=r["state"],
            last_checked_at=to_akl_iso(r["last_checked_at"]) if r["last_checked_at"] else None,
            last_success_at=to_akl_iso(r["last_success_at"]) if r["last_success_at"] else None,
            detail=r["detail"],
        )
        for r in conn.execute("SELECT * FROM source_health ORDER BY source")
    ]


def build_overview(
    conn: sqlite3.Connection, *, analysable_slugs: Collection[str], now: datetime
) -> OverviewOut:
    now_s = to_utc_iso(now)
    latest = conn.execute(
        "SELECT r.* FROM release r WHERE r.series_slug = ? AND EXISTS ("
        " SELECT 1 FROM vintage v WHERE v.release_id = r.id) ORDER BY r.published_at DESC LIMIT 1",
        (SLUG,),
    ).fetchone()
    kpis: list[Kpi] = []
    featured = None
    if latest is not None:
        analysis = build_release_analysis(conn, latest["id"], analysable_slugs=analysable_slugs)
        if analysis is not None:
            kpis = [
                Kpi(
                    metric=m,
                    release_id=latest["id"],
                    published_at=analysis.release.published_at,
                    source_url=latest["page_url"],
                )
                for m in analysis.headline_metrics
            ]
            featured = FeaturedOut(
                release=analysis.release,
                headline=analysis.release.headline,
                first_insight=analysis.executive_summary[0].text
                if analysis.executive_summary
                else None,
            )

    def summaries(sql: str, params: tuple) -> list:
        return [
            release_summary(conn, r, analysable_slugs=analysable_slugs)
            for r in conn.execute(sql, params)
        ]

    published = summaries(
        "SELECT * FROM release WHERE status IN ('published', 'corrected') AND published_at <= ?"
        " ORDER BY published_at DESC LIMIT 8",
        (now_s,),
    )
    upcoming = summaries(
        "SELECT * FROM release WHERE status IN ('scheduled', 'delayed') AND published_at >= ?"
        " ORDER BY published_at ASC LIMIT 10",
        (now_s,),
    )
    return OverviewOut(
        generated_at=to_akl_iso(now),
        kpis=kpis,
        latest_releases=published,
        upcoming=upcoming,
        freshness=health_rows(conn),
        featured=featured,
        inactive_categories=[InactiveCategory(name=n, reason=r) for n, r in INACTIVE_CATEGORIES],
    )
