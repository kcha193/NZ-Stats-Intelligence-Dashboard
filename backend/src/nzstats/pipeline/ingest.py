"""discover -> fetch -> validate -> normalise -> persist, with last-known-good preserved."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from nzstats.adapters.base import Adapter, ParsedBundle
from nzstats.clock import AKL, from_utc_iso, utc_now
from nzstats.domain import (
    ErrorClass,
    IngestError,
    Observation,
    ReleaseStatus,
    RequestRefused,
    SeriesDef,
)
from nzstats.pipeline.discover import attempt, record_batch_health
from nzstats.runtime import Runtime
from nzstats.slug import slugify
from nzstats.sources.calendar import fetch_release_month
from nzstats.sources.release_page import parse_release_page, pick_downloads
from nzstats.stats.periods import month_range
from nzstats.store import repo
from nzstats.store.db import transaction

log = logging.getLogger(__name__)

HTML = ("text/html",)
DATA_TYPES = (
    "text/csv",
    "application/octet-stream",
    "text/plain",
    "application/vnd.ms-excel",
    "application/zip",
    "application/x-zip-compressed",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


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
    except RequestRefused as exc:
        # Nothing was sent. Recording a run would spend the release's finite polling budget on an
        # attempt that never happened (the planner counts runs), so report it and leave no trace.
        return IngestOutcome(release_key, "failed", exc.error_class, str(exc))
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


def _bundle_digest(
    series: Iterable[tuple[SeriesDef, Iterable[Observation | repo.ObservationRow]]],
) -> str:
    """Versioned statistical identity, independent of source titles, markup and CSV formatting."""
    data = []
    for definition, observations in series:
        points = sorted(
            (
                o.period,
                float(o.value) if o.value != 0 else 0.0,
                o.status.value,
                (float(o.std_error) if o.std_error != 0 else 0.0)
                if o.std_error is not None
                else None,
                o.released_in,
            )
            for o in observations
        )
        data.append(
            (
                definition.key,
                definition.unit,
                definition.frequency.value,
                definition.adjustment.value,
                definition.definition_id,
                points,
            )
        )
    payload = json.dumps(sorted(data), separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return "data-v1:" + hashlib.sha256(payload.encode()).hexdigest()


def _matching_bundle(conn: sqlite3.Connection, release_id: int, digest: str) -> str | None:
    for stored in repo.release_bundles(conn, release_id):
        if stored == digest:
            return stored
        # Older databases used source bytes (or, for ECT, also definition wording) as identity.
        # Compare retained observations and measurement identity rather than rewriting history or
        # manufacturing a correction on upgrade.
        if _bundle_digest(repo.bundle_series(conn, release_id, stored)) == digest:
            return stored
    return None


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

    wanted = pick_downloads(page.download_urls, adapter.required_downloads)
    missing = [k for k in adapter.required_downloads if k not in wanted]
    if missing:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, f"release page lists no {missing} download")

    files: dict[str, bytes] = {}
    for kind, url in wanted.items():
        result = rt.fetcher.get(url, expect=DATA_TYPES)
        record = rt.artifacts.save(result)
        repo.record_artifact(rt.conn, record)
        files[kind] = result.body
    optional_notes: list[str] = []
    for kind in getattr(adapter, "optional_downloads", ()):
        url = pick_downloads(page.download_urls, (kind,)).get(kind)
        if url is None:
            optional_notes.append(f"optional {kind} download is not listed")
            continue
        try:
            result = rt.fetcher.get(url, expect=DATA_TYPES)
        except RequestRefused:
            raise
        except IngestError as exc:
            if exc.error_class is ErrorClass.BLOCKED:
                raise
            optional_notes.append(f"optional {kind} download unavailable ({exc.error_class.value})")
            continue
        repo.record_artifact(rt.conn, rt.artifacts.save(result))
        files[kind] = result.body
    release_id = int(row["id"])
    bundle = adapter.parse(page, files)
    published_at = from_utc_iso(row["published_at"])
    previous = {
        k: repo.previous_points(
            rt.conn,
            k,
            published_at,
            include_publication=adapter.preserve_publication_coverage,
        )
        for k in adapter.previous_keys
    }
    findings = adapter.validate(bundle, reference_period=row["reference_period"], previous=previous)
    errors = [f for f in findings if f.severity == "error"]
    if errors:
        raise IngestError(
            ErrorClass.VALIDATION_FAILED,
            "; ".join(f"[{f.rule}] {f.message}" for f in errors[:5]),
        )

    bundle_sha = _bundle_digest((ps.definition, ps.observations) for ps in bundle.series)
    optional_prefixes = tuple(getattr(adapter, "optional_series_prefixes", ()))
    # Optional data coming or going is not something Stats NZ published or corrected, but a failed
    # optional input is still reported, including on the fast path: an enriched bundle keeps its
    # required-only digest, so a later optional failure parses to exactly that digest.
    # Validation warnings (for example a release that publishes no contribution charts) describe the
    # stored data just as much as an ingest that wrote it, so every unchanged repeat reports them
    # too instead of recording a clean success. Adapters without optional inputs keep quiet repeats.
    all_warnings = tuple(
        dict.fromkeys(
            (
                *optional_notes,
                *bundle.warnings,
                *(f.message for f in findings if f.severity == "warning"),
            )
        )
    )
    unchanged_warnings = all_warnings if optional_prefixes else ()
    if repo.release_bundle(rt.conn, release_id) == bundle_sha:
        return IngestOutcome(key, "unchanged", warnings=unchanged_warnings)
    now = now_fn()
    created = 0
    official = True  # False when only optional series were added to an already stored bundle
    with transaction(rt.conn):
        # Evaluated inside the write transaction: a second process may have committed this same
        # release between the pre-check above and here.
        had_vintages = repo.has_any_vintage(rt.conn, release_id)
        active = repo.release_bundle(rt.conn, release_id)
        matching = _matching_bundle(rt.conn, release_id, bundle_sha)
        enrich = False
        if matching is None and optional_prefixes:
            matching, enrich = _optional_match(rt.conn, release_id, bundle, optional_prefixes)
        if matching is not None and matching == active and not enrich:
            return IngestOutcome(key, "unchanged", warnings=unchanged_warnings)
        if matching is not None:
            # Content the release already has (it reverted to earlier content, or only optional
            # data differs by availability): its vintages exist, so core series are never copied.
            if enrich:
                created += _write_vintages(
                    rt.conn, release_id, matching, now, bundle, optional_prefixes
                )
            if matching != active:
                created += repo.reactivate_bundle(rt.conn, release_id, matching)
            else:
                official = False
        else:
            created = _write_vintages(rt.conn, release_id, bundle_sha, now, bundle)
        if created and official:
            repo.set_release_headline(rt.conn, key, page.headline, page_url)
            repo.set_release_status(
                rt.conn,
                key,
                ReleaseStatus.CORRECTED if had_vintages else ReleaseStatus.PUBLISHED,
                now,
            )
    if not created:
        return IngestOutcome(key, "unchanged", warnings=unchanged_warnings)
    return IngestOutcome(key, "ingested", warnings=all_warnings)


def _required_digest(
    series: Iterable[tuple[SeriesDef, Iterable[Observation | repo.ObservationRow]]],
    optional_prefixes: tuple[str, ...],
) -> str:
    """Statistical identity of the required series alone: optional series never change it."""
    return _bundle_digest((d, o) for d, o in series if not d.key.startswith(optional_prefixes))


def _optional_match(
    conn: sqlite3.Connection,
    release_id: int,
    bundle: ParsedBundle,
    optional_prefixes: tuple[str, ...],
) -> tuple[str | None, bool]:
    """A stored bundle holding exactly the same required statistics, as `(bundle, enrich)`.

    The new bundle may lack optional series the stored one has (a failed or invalid optional
    download): the stored bundle stands. It may carry optional series a stored bundle lacks (the
    optional download arrived later): `enrich` says to add them to that bundle. A stored bundle
    whose optional series differ from the new ones is not a match: that is a real revision.
    """
    fresh = [(ps.definition, ps.observations) for ps in bundle.series]
    required = _required_digest(fresh, optional_prefixes)
    offered = any(d.key.startswith(optional_prefixes) for d, _ in fresh)
    for stored in repo.release_bundles(conn, release_id):  # newest activation first
        series = repo.bundle_series(conn, release_id, stored)
        if _required_digest(series, optional_prefixes) != required:
            continue
        if not offered:
            return stored, False
        if not any(d.key.startswith(optional_prefixes) for d, _ in series):
            return stored, True
    return None, False


def _write_vintages(
    conn: sqlite3.Connection,
    release_id: int,
    bundle_sha: str,
    now: datetime,
    bundle: ParsedBundle,
    only_prefixes: tuple[str, ...] | None = None,
) -> int:
    """Insert one vintage per series (only those with a matching key prefix, if given)."""
    created = 0
    for ps in bundle.series:
        if only_prefixes is not None and not ps.definition.key.startswith(only_prefixes):
            continue
        series_id = repo.upsert_series(conn, ps.definition)
        vintage_id = repo.create_vintage(
            conn, release_id, series_id, now, "release_files", bundle.layout_version, bundle_sha
        )
        if vintage_id is not None:
            repo.insert_observations(conn, vintage_id, ps.observations)
            created += 1
    return created


def backfill(
    rt: Runtime,
    *,
    since: str,
    until: str | None = None,
    series_slug: str | None = None,
    now_fn: Callable[[], datetime] = utc_now,
) -> list[IngestOutcome]:
    """Ingest published releases with reference periods in inclusive `since`..`until` bounds.

    The calendar groups by publication month, so discovery scans through the current Auckland
    month to find delayed publications, retaining only references in the requested interval.
    Missing reference periods are excluded. Invalid or reversed bounds raise ValueError before
    any requests or writes. Stored releases are ingested oldest first.
    """
    if series_slug is not None and series_slug not in rt.adapters:
        raise ValueError("series_slug must have a registered release adapter")
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
    slugs = [series_slug] if series_slug else list(rt.adapters)
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
