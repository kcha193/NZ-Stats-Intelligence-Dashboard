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
from nzstats.pipeline.discover import attempt, record_batch_health
from nzstats.runtime import Runtime
from nzstats.slug import slugify
from nzstats.sources.calendar import fetch_release_month
from nzstats.sources.release_page import ReleasePage, classify_download, parse_release_page
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
    if outcome.outcome in ("ingested", "unchanged", "failed"):
        _refresh_release_health(rt, row["series_slug"], finished)
    return outcome


def _refresh_release_health(rt: Runtime, series_slug: str, now: datetime) -> None:
    """Health of a series' release ingestion follows the releases whose latest run failed, so one
    release succeeding cannot hide another that is still failing (and recovers only when it does)."""
    failing = repo.failing_releases(rt.conn, series_slug)
    shown = [f"{r['release_key']}: {r['detail'] or 'failed'}" for r in failing[:3]]
    if len(failing) > len(shown):
        shown.append(f"and {len(failing) - len(shown)} more")
    repo.set_source_health(
        rt.conn,
        f"release:{series_slug}",
        now,
        ok=not failing,
        detail="; ".join(shown) or None,
    )


def _bundle_digest(file_digests: list[str], page: ReleasePage) -> str:
    """Identity of everything `adapter.parse` reads: the downloaded files and the chart data embedded
    in the release page. Only chart titles and CSV bodies are hashed, never the surrounding HTML, so
    rotating nonces, markup or script changes cannot create a false revision, while a corrected or
    newly added chart (e.g. the optional citizenship series) does."""
    charts = sorted(hashlib.sha256(f"{c.title}\0{c.csv}".encode()).hexdigest() for c in page.charts)
    parts = ["files", *sorted(file_digests), "charts", *charts]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


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
    bundle_sha = _bundle_digest(digests, page)

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
    created = 0
    with transaction(rt.conn):
        # Evaluated inside the write transaction: a second process may have committed this same
        # release between the pre-check above and here.
        had_vintages = repo.has_any_vintage(rt.conn, release_id)
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
                created += 1
        if created:
            repo.set_release_headline(rt.conn, key, page.headline, page_url)
            repo.set_release_status(
                rt.conn,
                key,
                ReleaseStatus.CORRECTED if had_vintages else ReleaseStatus.PUBLISHED,
                now,
            )
    if not created:
        return IngestOutcome(key, "unchanged")
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
    # A month whose discovery failed may hide releases, so it is reported as a failure of its own
    # rather than left as a silent gap in an otherwise successful run.
    failures: list[IngestOutcome] = []
    month_errors: list[str] = []
    for month in month_range(since, until):
        errors: list[str] = []
        attempt(
            rt,
            "calendar_month",
            now_fn,
            lambda m=month: fetch_release_month(rt.fetcher, s.base_url, s.release_month_path, m),
            errors,
            record_health=False,
        )
        if errors:
            failures.append(
                IngestOutcome(f"calendar_month:{month}", "failed", detail="; ".join(errors))
            )
            month_errors.extend(errors)
    record_batch_health(rt, "calendar_month", now_fn, month_errors)
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
    return [*failures, *(ingest_release(rt, k, now_fn=now_fn) for k in keys)]
