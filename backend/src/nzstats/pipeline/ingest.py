"""discover -> fetch -> validate -> normalise -> persist, with last-known-good preserved."""

from __future__ import annotations

import hashlib
import logging
import re
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
    return outcome


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
    # Unchanged only while this bundle is also the release's current one; a revert to an earlier
    # bundle is new information and is validated and reactivated below.
    if repo.release_bundle(rt.conn, release_id) == bundle_sha:
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
        if repo.release_bundle(rt.conn, release_id) == bundle_sha:
            return IngestOutcome(key, "unchanged")
        if repo.has_vintage(rt.conn, release_id, bundle_sha):
            # The release reverted to content it published earlier: its vintages already exist.
            created = repo.reactivate_bundle(rt.conn, release_id, bundle_sha)
        else:
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
    """Ingest published releases with reference periods in inclusive `since`..`until` bounds.

    The calendar groups by publication month, so discovery scans through the current Auckland
    month to find delayed publications, retaining only references in the requested interval.
    Missing reference periods are excluded. Invalid or reversed bounds raise ValueError before
    any requests or writes. Stored releases are ingested oldest first.
    """
    for name, value in (("since", since), ("until", until)):
        if name == "until" and value is None:
            continue
        if (
            not isinstance(value, str)
            or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value)
            or value.startswith("0000-")
        ):
            raise ValueError(f"{name} must be a valid YYYY-MM month")
    local_now = now_fn().astimezone(AKL)
    current_month = f"{local_now.year:04d}-{local_now.month:02d}"
    if until is None:
        until = current_month
    if since > until:
        raise ValueError("since must not be after until")
    s = rt.settings
    # A month whose discovery failed may hide releases, so it is reported as a failure of its own
    # rather than left as a silent gap in an otherwise successful run.
    failures: list[IngestOutcome] = []
    month_errors: list[str] = []
    for month in month_range(since, max(until, current_month)):
        errors: list[str] = []
        attempt(
            rt,
            "calendar_month",
            now_fn,
            lambda m=month: [
                ref
                for ref in fetch_release_month(rt.fetcher, s.base_url, s.release_month_path, m)
                if ref.reference_period is not None and since <= ref.reference_period <= until
            ],
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
            f" AND reference_period >= ? AND reference_period <= ?"
            f" AND status IN ('published', 'corrected')"
            f" ORDER BY published_at",
            (*slugs, since, until),
        )
    ]
    return [*failures, *(ingest_release(rt, k, now_fn=now_fn) for k in keys)]
