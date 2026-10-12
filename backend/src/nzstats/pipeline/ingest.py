"""discover -> fetch -> validate -> normalise -> persist, with last-known-good preserved."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from nzstats.adapters.base import Adapter
from nzstats.clock import AKL, from_utc_iso, utc_now
from nzstats.domain import ErrorClass, IngestError, ReleaseStatus
from nzstats.pipeline.discover import attempt
from nzstats.runtime import Runtime
from nzstats.slug import slugify
from nzstats.sources.calendar import fetch_release_month
from nzstats.sources.release_page import classify_download, parse_release_page
from nzstats.stats.periods import month_range
from nzstats.store import repo
from nzstats.store.db import transaction

log = logging.getLogger(__name__)

HTML = ("text/html",)
DATA_TYPES = ("text/csv", "application/octet-stream", "text/plain", "application/vnd.ms-excel")


@dataclass(frozen=True)
class IngestOutcome:
    release_key: str
    outcome: str  # ingested | unchanged | not_available | failed | skipped_no_adapter
    error_class: ErrorClass | None = None
    detail: str | None = None
    warnings: tuple[str, ...] = ()


def ingest_release(
    rt: Runtime, release_key: str, *, now_fn: Callable[[], datetime] = utc_now
) -> IngestOutcome:
    row = repo.get_release(rt.conn, release_key)
    if row is None:
        raise KeyError(f"unknown release {release_key!r}")
    adapter = rt.adapters.get(row["series_slug"])
    if adapter is None:
        return IngestOutcome(release_key, "skipped_no_adapter")
    started = now_fn()
    try:
        outcome = _ingest(rt, row, adapter, now_fn)
    except IngestError as exc:
        kind = "not_available" if exc.error_class is ErrorClass.NOT_FOUND else "failed"
        outcome = IngestOutcome(release_key, kind, exc.error_class, str(exc))
    except Exception as exc:  # classified and recorded, never silently swallowed
        log.exception("unexpected error ingesting %s", release_key)
        outcome = IngestOutcome(
            release_key,
            "failed",
            ErrorClass.UNEXPECTED,
            f"unexpected {type(exc).__name__}; see server log",
        )
    finished = now_fn()
    detail = outcome.detail
    if outcome.warnings:
        detail = "; ".join(filter(None, [detail, "warnings: " + " | ".join(outcome.warnings)]))
    repo.record_ingest_run(
        rt.conn,
        release_key,
        started,
        finished,
        outcome.outcome,
        outcome.error_class.value if outcome.error_class else None,
        detail,
    )
    source = f"release:{row['series_slug']}"
    if outcome.outcome in ("ingested", "unchanged"):
        repo.set_source_health(rt.conn, source, finished, ok=True, detail=None)
    elif outcome.outcome == "failed":
        repo.set_source_health(rt.conn, source, finished, ok=False, detail=detail)
    return outcome


def _ingest(
    rt: Runtime, row: sqlite3.Row, adapter: Adapter, now_fn: Callable[[], datetime]
) -> IngestOutcome:
    key, settings = row["release_key"], rt.settings
    page_url = row["page_url"] or settings.base_url + settings.release_page_path.format(
        slug=slugify(row["title"])
    )

    page_result = rt.fetcher.get(page_url, expect=HTML)
    repo.record_artifact(rt.conn, rt.artifacts.save(page_result))
    page = parse_release_page(page_result.body.decode("utf-8"), settings.base_url)

    wanted: dict[str, str] = {}
    for url in page.download_urls:
        kind = classify_download(url)
        if kind in adapter.required_downloads and kind not in wanted:
            wanted[kind] = url
    missing = [k for k in adapter.required_downloads if k not in wanted]
    if missing:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, f"release page lists no {missing} download")

    files: dict[str, bytes] = {}
    digests: list[str] = []
    for kind, url in wanted.items():
        result = rt.fetcher.get(url, expect=DATA_TYPES)
        record = rt.artifacts.save(result)
        repo.record_artifact(rt.conn, record)
        files[kind] = result.body
        digests.append(record.sha256)
    bundle_sha = hashlib.sha256("".join(sorted(digests)).encode()).hexdigest()

    release_id = int(row["id"])
    if repo.has_vintage(rt.conn, release_id, bundle_sha):
        return IngestOutcome(key, "unchanged")

    bundle = adapter.parse(page, files)
    published_at = from_utc_iso(row["published_at"])
    previous = {k: repo.previous_points(rt.conn, k, published_at) for k in adapter.previous_keys}
    findings = adapter.validate(bundle, reference_period=row["reference_period"], previous=previous)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        raise IngestError(
            ErrorClass.VALIDATION_FAILED,
            "; ".join(f"[{f.rule}] {f.message}" for f in errors[:5]),
        )

    now = now_fn()
    corrected = repo.has_any_vintage(rt.conn, release_id)
    with transaction(rt.conn):
        for ps in bundle.series:
            series_id = repo.upsert_series(rt.conn, ps.definition)
            vintage_id = repo.create_vintage(
                rt.conn,
                release_id,
                series_id,
                now,
                "release_files",
                bundle.layout_version,
                bundle_sha,
            )
            if vintage_id is not None:
                repo.insert_observations(rt.conn, vintage_id, ps.observations)
        repo.set_release_headline(rt.conn, key, page.headline, page_url)
        repo.set_release_status(
            rt.conn, key, ReleaseStatus.CORRECTED if corrected else ReleaseStatus.PUBLISHED, now
        )
    return IngestOutcome(
        key, "ingested", warnings=tuple(f.message for f in findings if f.severity == "warning")
    )


def backfill(
    rt: Runtime,
    *,
    since: str,
    until: str | None = None,
    now_fn: Callable[[], datetime] = utc_now,
) -> list[IngestOutcome]:
    """Ingest every published release whose reference period is >= `since`, oldest first."""
    s = rt.settings
    local_now = now_fn().astimezone(AKL)
    until = until or f"{local_now.year:04d}-{local_now.month:02d}"
    errors: list[str] = []
    for month in month_range(since, until):
        attempt(
            rt,
            "calendar_month",
            now_fn,
            lambda m=month: fetch_release_month(rt.fetcher, s.base_url, s.release_month_path, m),
            errors,
        )
    slugs = list(rt.adapters)
    marks = ",".join("?" * len(slugs))
    keys = [
        r["release_key"]
        for r in rt.conn.execute(
            f"SELECT release_key FROM release WHERE series_slug IN ({marks})"
            f" AND reference_period >= ? AND status IN ('published', 'corrected')"
            f" ORDER BY published_at",
            (*slugs, since),
        )
    ]
    return [ingest_release(rt, k, now_fn=now_fn) for k in keys]
