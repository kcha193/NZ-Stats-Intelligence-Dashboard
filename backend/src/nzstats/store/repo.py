"""All SQL lives here. Timestamps in/out are UTC ISO strings (see clock.py)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from nzstats.clock import to_utc_iso
from nzstats.domain import (
    Adjustment,
    Frequency,
    Observation,
    ObsStatus,
    Point,
    ReleaseRef,
    ReleaseStatus,
    SeriesDef,
)

# A missing file is meaningful only once it represents an unresolved data gap.
DATA_GAP_STATUSES = ("published", "corrected", "unavailable")
INGEST_SUCCESSES = ("ingested", "unchanged")


@dataclass(frozen=True)
class ArtifactRecord:
    url: str
    sha256: str
    fetched_at: datetime
    http_status: int
    content_type: str | None
    size_bytes: int
    path: str


@dataclass(frozen=True)
class VintageInfo:
    vintage_id: int
    release_key: str
    title: str
    published_at: str
    captured_at: str
    source_kind: str
    layout_version: str


def upsert_release(conn: sqlite3.Connection, ref: ReleaseRef, now: datetime) -> int:
    now_s, pub = to_utc_iso(now), to_utc_iso(ref.published_at)
    row = conn.execute("SELECT * FROM release WHERE release_key = ?", (ref.release_key,)).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO release(release_key, series_slug, title, period_label, reference_period,"
            " published_at, status, page_url, headline, statsnz_id, first_seen_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ref.release_key,
                ref.series_slug,
                ref.title,
                ref.period_label,
                ref.reference_period,
                pub,
                ref.status.value,
                ref.page_url,
                ref.headline,
                ref.statsnz_id,
                now_s,
                now_s,
            ),
        )
        return int(cur.lastrowid)

    status = ReleaseStatus(row["status"])
    published_at = row["published_at"]
    if ref.status is ReleaseStatus.PUBLISHED:
        status = ReleaseStatus.PUBLISHED if status is not ReleaseStatus.CORRECTED else status
        published_at = pub
    elif status in (ReleaseStatus.SCHEDULED, ReleaseStatus.DELAYED, ReleaseStatus.UNAVAILABLE):
        # The ICS and month feeds are read one after the other and neither is reliably fresher, so an
        # unpublished release's slot only ever moves later: it converges on the latest slot any feed
        # reported, in whatever order they are read, and a stale feed cannot rewind a reschedule.
        # A later slot also puts an `unavailable` release back into polling (attempts count from the
        # new slot). A release that really comes out early is picked up once the calendar lists it
        # as published, which sets its actual time above.
        if pub > published_at:
            status = ReleaseStatus.DELAYED
            published_at = pub
    conn.execute(
        "UPDATE release SET title=?, period_label=?, reference_period=?, published_at=?, status=?,"
        " page_url=COALESCE(?, page_url), headline=COALESCE(?, headline),"
        " statsnz_id=COALESCE(?, statsnz_id), updated_at=? WHERE id=?",
        (
            ref.title,
            ref.period_label,
            ref.reference_period,
            published_at,
            status.value,
            ref.page_url,
            ref.headline,
            ref.statsnz_id,
            now_s,
            row["id"],
        ),
    )
    if status.value != row["status"]:
        _refresh_release_health(conn, row["series_slug"])
    return int(row["id"])


def get_release(conn: sqlite3.Connection, release_key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM release WHERE release_key = ?", (release_key,)).fetchone()


def set_release_status(
    conn: sqlite3.Connection, release_key: str, status: ReleaseStatus, now: datetime
) -> None:
    conn.execute(
        "UPDATE release SET status=?, updated_at=? WHERE release_key=?",
        (status.value, to_utc_iso(now), release_key),
    )
    row = get_release(conn, release_key)
    if row is not None:
        _refresh_release_health(conn, row["series_slug"])


def set_release_headline(
    conn: sqlite3.Connection, release_key: str, headline: str | None, page_url: str | None
) -> None:
    conn.execute(
        "UPDATE release SET headline=COALESCE(?, headline), page_url=COALESCE(?, page_url)"
        " WHERE release_key=?",
        (headline, page_url, release_key),
    )


def upsert_series(conn: sqlite3.Connection, d: SeriesDef) -> int:
    conn.execute(
        "INSERT INTO series(key, name, unit, frequency, seasonal_adjustment, definition,"
        " definition_id, category, source_url) VALUES (?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(key) DO UPDATE SET name=excluded.name, unit=excluded.unit,"
        " frequency=excluded.frequency, seasonal_adjustment=excluded.seasonal_adjustment,"
        " definition=excluded.definition, definition_id=excluded.definition_id,"
        " category=excluded.category, source_url=excluded.source_url",
        (
            d.key,
            d.name,
            d.unit,
            d.frequency.value,
            d.adjustment.value,
            d.definition,
            d.definition_id,
            d.category,
            d.source_url,
        ),
    )
    return int(conn.execute("SELECT id FROM series WHERE key=?", (d.key,)).fetchone()[0])


def record_artifact(conn: sqlite3.Connection, rec: ArtifactRecord) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO raw_artifact(url, sha256, fetched_at, http_status, content_type,"
        " size_bytes, path) VALUES (?,?,?,?,?,?,?)",
        (
            rec.url,
            rec.sha256,
            to_utc_iso(rec.fetched_at),
            rec.http_status,
            rec.content_type,
            rec.size_bytes,
            rec.path,
        ),
    )
    return int(
        conn.execute(
            "SELECT id FROM raw_artifact WHERE url=? AND sha256=?", (rec.url, rec.sha256)
        ).fetchone()[0]
    )


def create_vintage(
    conn: sqlite3.Connection,
    release_id: int,
    series_id: int,
    captured_at: datetime,
    source_kind: str,
    layout_version: str,
    bundle_sha256: str,
) -> int | None:
    cur = conn.execute(
        "INSERT OR IGNORE INTO vintage(release_id, series_id, captured_at, source_kind,"
        " layout_version, bundle_sha256, activation)"
        " VALUES (?,?,?,?,?,?, (SELECT COALESCE(MAX(activation), 0) + 1 FROM vintage))",
        (
            release_id,
            series_id,
            to_utc_iso(captured_at),
            source_kind,
            layout_version,
            bundle_sha256,
        ),
    )
    return int(cur.lastrowid) if cur.rowcount else None


def insert_observations(
    conn: sqlite3.Connection, vintage_id: int, obs: Iterable[Observation]
) -> int:
    rows = [
        (vintage_id, o.period, o.value, o.status.value, o.std_error, o.released_in) for o in obs
    ]
    conn.executemany(
        "INSERT INTO observation(vintage_id, period, value, status, std_error, released_in)"
        " VALUES (?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def has_vintage(conn: sqlite3.Connection, release_id: int, bundle_sha256: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM vintage WHERE release_id=? AND bundle_sha256=? LIMIT 1",
            (release_id, bundle_sha256),
        ).fetchone()
        is not None
    )


def reactivate_bundle(conn: sqlite3.Connection, release_id: int, bundle_sha256: str) -> int:
    """Make an already stored bundle the release's current one again; returns vintages touched.

    A release can revert to content it published before. Its vintages already exist, so nothing is
    inserted: they are moved to the newest activation, which is what every "latest" query orders by.
    """
    cur = conn.execute(
        "UPDATE vintage SET activation = (SELECT MAX(activation) + 1 FROM vintage)"
        " WHERE release_id = ? AND bundle_sha256 = ?",
        (release_id, bundle_sha256),
    )
    return cur.rowcount


def has_any_vintage(conn: sqlite3.Connection, release_id: int) -> bool:
    return (
        conn.execute("SELECT 1 FROM vintage WHERE release_id=? LIMIT 1", (release_id,)).fetchone()
        is not None
    )


_VINTAGE_ORDER = "r.published_at, v.activation, v.id"


def list_vintages(conn: sqlite3.Connection, series_key: str) -> list[VintageInfo]:
    rows = conn.execute(
        f"SELECT v.id, r.release_key, r.title, r.published_at, v.captured_at, v.source_kind,"
        f" v.layout_version FROM vintage v JOIN release r ON r.id=v.release_id"
        f" JOIN series s ON s.id=v.series_id WHERE s.key=? ORDER BY {_VINTAGE_ORDER}",
        (series_key,),
    ).fetchall()
    return [VintageInfo(*tuple(r)) for r in rows]


def vintage_points(conn: sqlite3.Connection, vintage_id: int) -> dict[str, Point]:
    rows = conn.execute(
        "SELECT period, value, status FROM observation WHERE vintage_id=? ORDER BY period",
        (vintage_id,),
    ).fetchall()
    return {r["period"]: Point(r["period"], r["value"], ObsStatus(r["status"])) for r in rows}


def latest_points(conn: sqlite3.Connection, series_key: str) -> dict[str, Point]:
    infos = list_vintages(conn, series_key)
    return vintage_points(conn, infos[-1].vintage_id) if infos else {}


def latest_bundle(conn: sqlite3.Connection, series_key: str) -> tuple[int, str] | None:
    """(release id, bundle digest) of a series' latest vintage, in the order `list_vintages` uses."""
    row = conn.execute(
        "SELECT v.release_id, v.bundle_sha256 FROM vintage v JOIN release r ON r.id=v.release_id"
        " JOIN series s ON s.id=v.series_id WHERE s.key=? ORDER BY r.published_at DESC, v.activation DESC, v.id DESC"
        " LIMIT 1",
        (series_key,),
    ).fetchone()
    return (row["release_id"], row["bundle_sha256"]) if row else None


def bundle_points(
    conn: sqlite3.Connection, series_key: str, bundle: tuple[int, str]
) -> dict[str, Point]:
    """Points a series holds in one specific ingested bundle; empty if the bundle did not include it.

    A series absent from a release's files has no vintage in that bundle, and an older vintage of
    the same series (another release, or an earlier bundle of the same release) is not a substitute.
    """
    row = conn.execute(
        "SELECT v.id FROM vintage v JOIN series s ON s.id=v.series_id"
        " WHERE s.key=? AND v.release_id=? AND v.bundle_sha256=?",
        (series_key, *bundle),
    ).fetchone()
    return vintage_points(conn, row["id"]) if row else {}


def previous_points(
    conn: sqlite3.Connection,
    series_key: str,
    published_before: datetime,
    *,
    include_publication: bool = False,
) -> dict[str, Point]:
    cutoff = to_utc_iso(published_before)
    prior = [
        i
        for i in list_vintages(conn, series_key)
        if i.published_at < cutoff or (include_publication and i.published_at == cutoff)
    ]
    return vintage_points(conn, prior[-1].vintage_id) if prior else {}


def record_ingest_run(
    conn: sqlite3.Connection,
    release_key: str,
    started_at: datetime,
    finished_at: datetime,
    outcome: str,
    error_class: str | None,
    detail: str | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO ingest_run(release_key, started_at, finished_at, outcome, error_class,"
        " detail) VALUES (?,?,?,?,?,?)",
        (
            release_key,
            to_utc_iso(started_at),
            to_utc_iso(finished_at),
            outcome,
            error_class,
            detail,
        ),
    )
    row = get_release(conn, release_key)
    if row is not None:
        meaningful = (
            outcome in (*INGEST_SUCCESSES, "failed")
            or outcome == "not_available"
            and row["status"] in DATA_GAP_STATUSES
        )
        _refresh_release_health(
            conn, row["series_slug"], checked_at=finished_at if meaningful else None
        )
    return int(cur.lastrowid)


def failing_releases(conn: sqlite3.Connection, series_slug: str) -> list[sqlite3.Row]:
    """Latest meaningful outcome per release, with outstanding failures ordered by run ID.

    Classify before ranking: neutral retries and unsupported adapters cannot recover a failure.
    Interpret 404s against current status so publication, exhaustion and rescheduling can change
    health without another attempt. A later success always supersedes earlier failures and gaps.
    """
    return conn.execute(
        "WITH meaningful AS ("
        " SELECT run.id, run.release_key, run.outcome, run.detail,"
        " ROW_NUMBER() OVER (PARTITION BY run.release_key ORDER BY run.id DESC) AS rank"
        " FROM ingest_run run JOIN release r ON r.release_key = run.release_key"
        " WHERE r.series_slug = ? AND (run.outcome IN (?, ?, 'failed')"
        " OR (run.outcome = 'not_available' AND r.status IN (?, ?, ?))))"
        " SELECT release_key, detail FROM meaningful"
        " WHERE rank = 1 AND outcome IN ('failed', 'not_available') ORDER BY id",
        (series_slug, *INGEST_SUCCESSES, *DATA_GAP_STATUSES),
    ).fetchall()


def _refresh_release_health(
    conn: sqlite3.Connection, series_slug: str, *, checked_at: datetime | None = None
) -> None:
    """Refresh the projection at its write boundaries; only real checks advance timestamps."""
    failing = failing_releases(conn, series_slug)
    shown = [f"{r['release_key']}: {r['detail'] or 'failed'}" for r in failing[:3]]
    if len(failing) > len(shown):
        shown.append(f"and {len(failing) - len(shown)} more")
    source, detail = f"release:{series_slug}", "; ".join(shown) or None
    if checked_at is not None:
        set_source_health(conn, source, checked_at, ok=not failing, detail=detail)
    elif failing:
        conn.execute(
            "INSERT INTO source_health(source, state, detail) VALUES (?, 'degraded', ?)"
            " ON CONFLICT(source) DO UPDATE SET state=excluded.state, detail=excluded.detail",
            (source, detail),
        )
    else:
        # No new healthy row for neutral-only history; clearing a rescheduled gap is not a check.
        conn.execute("UPDATE source_health SET state='ok', detail=NULL WHERE source=?", (source,))


def set_source_health(
    conn: sqlite3.Connection, source: str, now: datetime, *, ok: bool, detail: str | None
) -> None:
    now_s = to_utc_iso(now)
    conn.execute(
        "INSERT INTO source_health(source, state, last_checked_at, last_success_at, detail)"
        " VALUES (?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET state=excluded.state,"
        " last_checked_at=excluded.last_checked_at,"
        " last_success_at=COALESCE(excluded.last_success_at, source_health.last_success_at),"
        " detail=excluded.detail",
        (source, "ok" if ok else "degraded", now_s, now_s if ok else None, detail),
    )


@dataclass(frozen=True)
class ObservationRow:
    period: str
    value: float
    status: ObsStatus
    std_error: float | None
    released_in: str | None


def get_series_row(
    conn: sqlite3.Connection, key: str, vintage_id: int | None = None
) -> sqlite3.Row | None:
    if vintage_id is None:
        vintages = list_vintages(conn, key)
        vintage_id = vintages[-1].vintage_id if vintages else None
    if vintage_id is not None:
        return conn.execute(
            "SELECT * FROM vintage_series_definition WHERE key=? AND vintage_id=?",
            (key, vintage_id),
        ).fetchone()
    return conn.execute("SELECT * FROM series WHERE key = ?", (key,)).fetchone()


def get_release_by_id(conn: sqlite3.Connection, release_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM release WHERE id = ?", (release_id,)).fetchone()


def vintage_observations(conn: sqlite3.Connection, vintage_id: int) -> dict[str, ObservationRow]:
    rows = conn.execute(
        "SELECT period, value, status, std_error, released_in FROM observation"
        " WHERE vintage_id = ? ORDER BY period",
        (vintage_id,),
    ).fetchall()
    return {
        r["period"]: ObservationRow(
            r["period"], r["value"], ObsStatus(r["status"]), r["std_error"], r["released_in"]
        )
        for r in rows
    }


def release_vintage(
    conn: sqlite3.Connection, series_key: str, release_id: int
) -> VintageInfo | None:
    row = conn.execute(
        "SELECT v.id, r.release_key, r.title, r.published_at, v.captured_at, v.source_kind,"
        " v.layout_version FROM vintage v JOIN release r ON r.id = v.release_id"
        " JOIN series s ON s.id = v.series_id WHERE s.key = ? AND v.release_id = ?"
        " ORDER BY v.activation DESC, v.id DESC LIMIT 1",
        (series_key, release_id),
    ).fetchone()
    return VintageInfo(*tuple(row)) if row else None


def release_bundle(conn: sqlite3.Connection, release_id: int) -> str | None:
    """Digest of the release's newest ingested bundle (a corrected re-ingest supersedes the first)."""
    row = conn.execute(
        "SELECT bundle_sha256 FROM vintage WHERE release_id = ?"
        " ORDER BY activation DESC, id DESC LIMIT 1",
        (release_id,),
    ).fetchone()
    return row["bundle_sha256"] if row else None


def release_bundles(conn: sqlite3.Connection, release_id: int) -> list[str]:
    """Distinct bundles, most recently activated first (including a reactivated earlier bundle)."""
    rows = conn.execute(
        "SELECT bundle_sha256 FROM vintage WHERE release_id = ? GROUP BY bundle_sha256"
        " ORDER BY MAX(activation) DESC, MAX(id) DESC",
        (release_id,),
    ).fetchall()
    return [r["bundle_sha256"] for r in rows]


def bundle_series(
    conn: sqlite3.Connection, release_id: int, bundle_sha256: str
) -> list[tuple[SeriesDef, list[ObservationRow]]]:
    """All series and observations from exactly one stored release bundle."""
    rows = conn.execute(
        "SELECT d.*, v.id AS vintage_id FROM vintage v"
        " JOIN vintage_series_definition d ON d.vintage_id=v.id"
        " WHERE v.release_id = ? AND v.bundle_sha256 = ? ORDER BY d.key",
        (release_id, bundle_sha256),
    ).fetchall()
    return [
        (
            SeriesDef(
                key=r["key"],
                name=r["name"],
                unit=r["unit"],
                frequency=Frequency(r["frequency"]),
                adjustment=Adjustment(r["seasonal_adjustment"]),
                definition=r["definition"],
                definition_id=r["definition_id"],
                category=r["category"],
                source_url=r["source_url"],
            ),
            list(vintage_observations(conn, r["vintage_id"]).values()),
        )
        for r in rows
    ]


def bundle_vintage(
    conn: sqlite3.Connection, series_key: str, release_id: int, bundle_sha256: str
) -> VintageInfo | None:
    """A series' vintage within one specific bundle of a release; None if the bundle lacks it."""
    row = conn.execute(
        "SELECT v.id, r.release_key, r.title, r.published_at, v.captured_at, v.source_kind,"
        " v.layout_version FROM vintage v JOIN release r ON r.id = v.release_id"
        " JOIN series s ON s.id = v.series_id"
        " WHERE s.key = ? AND v.release_id = ? AND v.bundle_sha256 = ?",
        (series_key, release_id, bundle_sha256),
    ).fetchone()
    return VintageInfo(*tuple(row)) if row else None


def bundle_captured_at(conn: sqlite3.Connection, release_id: int, bundle_sha256: str) -> str | None:
    """When the newest data in one stored bundle was captured.

    Optional series can join a bundle after it was first ingested, so this can be later than any
    single series' vintage, without the bundle (or the release) having been corrected.
    """
    row = conn.execute(
        "SELECT MAX(captured_at) FROM vintage WHERE release_id = ? AND bundle_sha256 = ?",
        (release_id, bundle_sha256),
    ).fetchone()
    return row[0]


def vintage_superseded(conn: sqlite3.Connection, vintage_id: int) -> bool:
    """True if the vintage's release was re-ingested into a newer bundle that does not include this
    series, so its values were withdrawn. A series that the newer bundle revised is not superseded:
    its older vintage is simply the original of a revision."""
    row = conn.execute(
        "WITH newest AS (SELECT release_id, bundle_sha256 FROM vintage"
        "  WHERE release_id = (SELECT release_id FROM vintage WHERE id = ?)"
        "  ORDER BY activation DESC, id DESC LIMIT 1)"
        " SELECT v.bundle_sha256 <> n.bundle_sha256 AND NOT EXISTS ("
        "  SELECT 1 FROM vintage w WHERE w.release_id = v.release_id AND w.series_id = v.series_id"
        "  AND w.bundle_sha256 = n.bundle_sha256) AS superseded"
        " FROM vintage v JOIN newest n ON n.release_id = v.release_id WHERE v.id = ?",
        (vintage_id, vintage_id),
    ).fetchone()
    return bool(row and row["superseded"])


def previous_vintage(
    conn: sqlite3.Connection, series_key: str, published_before_utc: str
) -> VintageInfo | None:
    prior = [i for i in list_vintages(conn, series_key) if i.published_at < published_before_utc]
    return prior[-1] if prior else None


def series_overview(conn: sqlite3.Connection, category_prefix: str | None = None) -> list[dict]:
    like = None if category_prefix is None else category_prefix + "%"
    rows = conn.execute(
        "SELECT s.*, (SELECT COUNT(*) FROM vintage v WHERE v.series_id = s.id) AS n_vintages,"
        " (SELECT MAX(o.period) FROM observation o WHERE o.vintage_id = ("
        "   SELECT v.id FROM vintage v JOIN release r ON r.id = v.release_id"
        "   WHERE v.series_id = s.id ORDER BY r.published_at DESC, v.activation DESC, v.id DESC LIMIT 1))"
        " AS latest_period FROM series s WHERE (? IS NULL OR s.category LIKE ?) ORDER BY s.key",
        (like, like),
    ).fetchall()
    return [dict(r) | dict(get_series_row(conn, r["key"])) for r in rows]
