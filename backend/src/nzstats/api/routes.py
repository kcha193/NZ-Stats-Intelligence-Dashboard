from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from nzstats.api.deps import Conn, Now
from nzstats.clock import AKL, to_akl_iso, to_utc_iso
from nzstats.insights.countries import rank_countries
from nzstats.insights.migration import build_release_analysis
from nzstats.insights.overview import build_overview, health_rows
from nzstats.insights.revisions import revision_view, series_out, vintage_out
from nzstats.insights.summary import release_summary
from nzstats.models import (
    CalendarOut,
    CountriesOut,
    HealthOut,
    OverviewOut,
    PointOut,
    ReleaseDetail,
    ReleaseSummary,
    RevisionsOut,
    RunOut,
    SeriesDataOut,
    SeriesOut,
)
from nzstats.store import repo

router = APIRouter()
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
CAVEATS = {
    "monthly": "Monthly estimates; provisional values are revised in later releases.",
    "rolling_annual": (
        "Rolling twelve-month total published by Stats NZ. Not comparable with monthly figures."
    ),
}


def _slugs(request: Request) -> set[str]:
    return request.app.state.analysable_slugs


@router.get("/health", response_model=HealthOut)
def health(conn: Conn, now: Now) -> HealthOut:
    runs = [
        RunOut(
            release_key=r["release_key"],
            started_at=to_akl_iso(r["started_at"]),
            outcome=r["outcome"],
            error_class=r["error_class"],
            detail=r["detail"],
        )
        for r in conn.execute("SELECT * FROM ingest_run ORDER BY id DESC LIMIT 15")
    ]
    counts = {
        r["status"]: r["n"]
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM release GROUP BY status")
    }
    return HealthOut(
        generated_at=to_akl_iso(now),
        database_ok=conn.execute("SELECT 1").fetchone()[0] == 1,
        sources=health_rows(conn),
        recent_runs=runs,
        release_counts=counts,
        series_count=conn.execute("SELECT COUNT(*) FROM series").fetchone()[0],
        vintage_count=conn.execute("SELECT COUNT(*) FROM vintage").fetchone()[0],
    )


@router.get("/overview", response_model=OverviewOut)
def overview(request: Request, conn: Conn, now: Now) -> OverviewOut:
    return build_overview(conn, analysable_slugs=_slugs(request), now=now)


@router.get("/releases", response_model=list[ReleaseSummary])
def releases(
    request: Request,
    conn: Conn,
    status: str | None = None,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ReleaseSummary]:
    statuses = [s for s in (status or "").split(",") if s]
    sql, params = "SELECT * FROM release", []
    if statuses:
        sql += f" WHERE status IN ({','.join('?' * len(statuses))})"
        params = statuses
    rows = conn.execute(sql + " ORDER BY published_at DESC, id DESC", params).fetchall()
    items = [release_summary(conn, r, analysable_slugs=_slugs(request)) for r in rows]
    if category:
        items = [i for i in items if i.category == category]
    return items[offset : offset + limit]


def _unavailable_reason(conn, row, summary: ReleaseSummary, analysable: set[str]) -> str:
    if row["series_slug"] not in analysable:
        return "Detailed analysis is not yet available for this category (planned for Phase 2)."
    if row["status"] in ("scheduled", "delayed"):
        word = "Delayed; now scheduled" if row["status"] == "delayed" else "Scheduled"
        return f"{word} for {summary.published_at[:16].replace('T', ' ')} (Pacific/Auckland)."
    if row["status"] == "unavailable":
        return "Stats NZ files were not available during the polling window; retrying daily."
    run = conn.execute(
        "SELECT * FROM ingest_run WHERE release_key = ? ORDER BY id DESC LIMIT 1",
        (row["release_key"],),
    ).fetchone()
    if run is None:
        return "Published, awaiting ingestion."
    if run["outcome"] in ("ingested", "unchanged") and not run["error_class"]:
        return (
            "The release was ingested, but the analysis could not be built from the stored data "
            "(a required series is missing for this release)."
        )
    extra = f": {run['error_class']}: {run['detail']}" if run["error_class"] else ""
    return f"Last ingestion attempt {run['outcome']}{extra}."


@router.get("/releases/{release_id}", response_model=ReleaseDetail)
def release_detail(release_id: int, request: Request, conn: Conn) -> ReleaseDetail:
    row = repo.get_release_by_id(conn, release_id)
    if row is None:
        raise HTTPException(404, "release not found")
    slugs = _slugs(request)
    summary = release_summary(conn, row, analysable_slugs=slugs)
    analysis = build_release_analysis(conn, release_id, analysable_slugs=slugs)
    reason = None if analysis else _unavailable_reason(conn, row, summary, slugs)
    return ReleaseDetail(release=summary, analysis=analysis, unavailable_reason=reason)


@router.get("/calendar", response_model=CalendarOut)
def calendar(
    request: Request,
    conn: Conn,
    now: Now,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> CalendarOut:
    today = now.astimezone(AKL).date()
    start = from_ or today - timedelta(days=45)
    end = to or today + timedelta(days=90)
    # Both bounds are whole Auckland days, `to` inclusive. date.min/date.max cannot be shifted by a
    # day or a UTC offset without overflowing, and nothing is stored outside them, so they mean
    # "unbounded" on that side.
    clauses, args = [], []
    if start > date.min:
        clauses.append("published_at >= ?")
        args.append(to_utc_iso(datetime.combine(start, time.min, AKL)))
    if end < date.max:
        clauses.append("published_at < ?")
        args.append(to_utc_iso(datetime.combine(end + timedelta(days=1), time.min, AKL)))
    rows = conn.execute(
        f"SELECT * FROM release WHERE {' AND '.join(clauses) or '1'} ORDER BY published_at, id",
        args,
    ).fetchall()
    health = {h.source: h for h in health_rows(conn)}
    sources = [health[s] for s in ("calendar_ics", "calendar_month") if s in health]
    return CalendarOut(
        items=[release_summary(conn, r, analysable_slugs=_slugs(request)) for r in rows],
        last_checked_at=max(
            (s.last_checked_at for s in sources if s.last_checked_at), default=None
        ),
        last_success_at=max(
            (s.last_success_at for s in sources if s.last_success_at), default=None
        ),
    )


@router.get("/series", response_model=list[SeriesOut])
def series_list(conn: Conn, category: str | None = None) -> list[SeriesOut]:
    return [
        series_out(r, r["n_vintages"], r["latest_period"])
        for r in repo.series_overview(conn, category)
    ]


def _vintage_for(conn, series_key: str, vintage: str | None) -> repo.VintageInfo:
    vintages = repo.list_vintages(conn, series_key)
    if not vintages:
        raise HTTPException(404, "series has no data")
    if vintage in (None, "latest"):
        return vintages[-1]
    matches = [v for v in vintages if v.release_key == vintage]
    if not matches:
        raise HTTPException(404, "vintage not found for this series")
    return matches[-1]


def _series_data(conn, key: str, vintage: str | None, from_: str | None, to: str | None):
    for value in (from_, to):
        if value is not None and not PERIOD.match(value):
            raise HTTPException(422, "from/to must be YYYY-MM")
    row = repo.get_series_row(conn, key)
    if row is None:
        raise HTTPException(404, "series not found")
    v = _vintage_for(conn, key, vintage)
    obs = repo.vintage_observations(conn, v.vintage_id)
    periods = [p for p in sorted(obs) if (not from_ or p >= from_) and (not to or p <= to)]
    return row, v, [obs[p] for p in periods], max(obs) if obs else None


@router.get("/series/{key}", response_model=SeriesDataOut)
def series_data(
    key: str,
    conn: Conn,
    vintage: str | None = None,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
) -> SeriesDataOut:
    row, v, obs, latest = _series_data(conn, key, vintage, from_, to)
    release = repo.get_release(conn, v.release_key)
    return SeriesDataOut(
        series=series_out(row, len(repo.list_vintages(conn, key)), latest),
        vintage=vintage_out(v),
        points=[
            PointOut(
                period=o.period,
                value=o.value,
                status=o.status.value,
                std_error=o.std_error,
                released_in=o.released_in,
            )
            for o in obs
        ],
        source_url=release["page_url"] if release else None,
        caveat=CAVEATS.get(row["frequency"], ""),
    )


# Spreadsheets skip leading whitespace, control and invisible characters before reading a formula, so
# the guard checks the first significant character. Mirrors `toCsv` in frontend/src/lib/csv.ts.
_LEADING_NOISE = re.compile(r"^[\s\x00-\x1f\x7f\xa0​-‏  ﻿]*")


def _csv_text(value: str) -> str:
    """Prefix text that a spreadsheet would run as a formula (upstream titles are not trusted)."""
    significant = _LEADING_NOISE.sub("", value, count=1)[:1]
    if value[:1] in ("\t", "\r", "\n") or (significant and significant in "=+-@"):
        return "'" + value
    return value


@router.get("/series/{key}/csv")
def series_csv(
    key: str,
    conn: Conn,
    vintage: str | None = None,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
) -> Response:
    row, v, obs, _ = _series_data(conn, key, vintage, from_, to)
    release = repo.get_release(conn, v.release_key)
    source = f"Stats NZ (CC BY 4.0) {release['page_url'] or ''}".strip()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "series_key",
            "series_name",
            "unit",
            "frequency",
            "period",
            "value",
            "status",
            "std_error",
            "released_in",
            "release",
            "published_at",
            "source",
        ]
    )
    for o in obs:
        writer.writerow(
            [
                _csv_text(key),
                _csv_text(row["name"]),
                _csv_text(row["unit"]),
                _csv_text(row["frequency"]),
                _csv_text(o.period),
                o.value,
                o.status.value,
                "" if o.std_error is None else o.std_error,
                _csv_text(o.released_in or ""),
                _csv_text(v.title),
                to_akl_iso(v.published_at),
                _csv_text(source),
            ]
        )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{key}.csv"'},
    )


@router.get("/revisions/{key}", response_model=RevisionsOut)
def revisions_view(
    key: str, conn: Conn, base: str | None = None, compare: str | None = None
) -> RevisionsOut:
    view = revision_view(conn, key, base_release_key=base, compare_release_key=compare)
    if view is None:
        raise HTTPException(404, "series or vintage not found")
    return view


@router.get("/migration/countries", response_model=CountriesOut)
def countries(
    conn: Conn,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
    top: Annotated[int, Query(ge=1, le=50)] = 15,
) -> CountriesOut:
    return rank_countries(conn, months=months, top=top)


@router.api_route("/{path:path}", methods=["GET"], include_in_schema=False)
def api_not_found(path: str) -> None:
    raise HTTPException(404, "not found")
