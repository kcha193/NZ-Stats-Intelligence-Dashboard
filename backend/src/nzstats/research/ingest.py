"""One research run for one institution: gate, discover, fetch, extract, validate, store.

Last-known-good: each document is written in its own transaction, and any failure (fetch, extraction,
validation or the write itself) is recorded as a run item while the previously stored version stays
current. A block stops the run. Nothing is requested for a source without recorded approval; a dry run
(allowed for `needs_review` sources, as the deliberate first probe) only discovers and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from nzstats.clock import to_utc_iso, utc_now
from nzstats.domain import ErrorClass, IngestError, RequestRefused
from nzstats.research import store
from nzstats.research.dates import DateParseError, PublishedDate, date_from_url, parse_published
from nzstats.research.discover import Candidate, discover
from nzstats.research.extract import Extracted, ExtractionLimits
from nzstats.research.extract_html import extract_html
from nzstats.research.extract_pdf import extract_pdf
from nzstats.research.fetch import Refused, ResearchFetcher
from nzstats.research.registry import ContentPolicy, Institution, ReviewStatus
from nzstats.research.safety import normalise_url
from nzstats.research.validate import PreviousVersion, safe_detail, validate_document
from nzstats.sources.artifacts import ArtifactStore
from nzstats.sources.fetcher import FetchResult
from nzstats.store.db import transaction
from nzstats.store.repo import record_artifact

log = logging.getLogger(__name__)

DOCUMENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "application/pdf",
    "application/octet-stream",
)


@dataclass(frozen=True)
class ItemOutcome:
    url: str
    outcome: str  # new|updated|unchanged|reactivated|duplicate|link_only|skipped_robots|skipped_unsafe|failed
    error_class: str | None = None
    detail: str | None = None
    publication_id: int | None = None
    version_id: int | None = None
    warnings: tuple[str, ...] = ()


@dataclass
class RunResult:
    institution: str
    outcome: str = "ok"  # ok|partial|failed|blocked|refused|dry_run
    refusal: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    items: list[ItemOutcome] = field(default_factory=list)
    discovery_errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(i.outcome for i in self.items))


class _StopRun(Exception):
    """The site is refusing or challenging us: record the item and request nothing more."""


def run_institution(
    conn: sqlite3.Connection,
    inst: Institution,
    fetcher: ResearchFetcher,
    *,
    artifacts: ArtifactStore | None = None,
    now_fn: Callable[[], datetime] = utc_now,
    dry_run: bool = False,
    limit: int | None = None,
    limits: ExtractionLimits | None = None,
) -> RunResult:
    result = RunResult(inst.key)
    refusal = refusal_for(inst, dry_run=dry_run)
    if refusal is not None:
        result.outcome, result.refusal = "refused", refusal
        return result
    started = now_fn()
    if not dry_run:
        with transaction(conn):
            inst_id = store.upsert_institution(
                conn, key=inst.key, name=inst.name, review_status=inst.review_status.value,
                content_policy=inst.content_policy.value, now=started,
            )  # fmt: skip
    found = discover(inst, fetcher)
    result.candidates, result.discovery_errors = found.candidates, found.errors
    if dry_run:
        result.outcome = "dry_run"
        return result
    cap = max(1, min(limit or inst.max_documents_per_run, inst.max_documents_per_run))
    blocked = fetcher.access_restricted
    for candidate in [] if blocked else found.candidates[:cap]:
        try:
            item = _one(conn, inst, inst_id, fetcher, candidate, artifacts, now_fn, limits)
        except _StopRun as stop:
            result.items.append(stop.args[0])
            blocked = True
            break
        result.items.append(item)
    result.outcome = _outcome(result, blocked or fetcher.access_restricted)
    _record(conn, inst_id, result, started, now_fn())
    return result


def refusal_for(inst: Institution, *, dry_run: bool) -> str | None:
    """Why this run may not make any request (fixed wording), or None."""
    if dry_run and inst.review_status is not ReviewStatus.RESTRICTED:
        return None if inst.content_policy is not ContentPolicy.NONE else inst.refusal_reason()
    return inst.refusal_reason()


def _failed(url: str, exc: BaseException, **kw) -> ItemOutcome:
    error_class = exc.error_class.value if isinstance(exc, IngestError) else "unexpected"
    return ItemOutcome(url, "failed", error_class, safe_detail(exc), **kw)


def _one(
    conn: sqlite3.Connection,
    inst: Institution,
    inst_id: int,
    fetcher: ResearchFetcher,
    candidate: Candidate,
    artifacts: ArtifactStore | None,
    now_fn: Callable[[], datetime],
    limits: ExtractionLimits | None,
) -> ItemOutcome:
    url = candidate.url
    doc_key = f"{inst.key}:{url.split('://', 1)[1]}"
    existing = conn.execute(
        "SELECT id FROM research_publication WHERE doc_key=?", (doc_key,)
    ).fetchone()
    if inst.content_policy is ContentPolicy.METADATA_ONLY:
        return _link_only(conn, inst, inst_id, candidate, doc_key, existing is not None, now_fn())
    try:
        fetched = fetcher.get(url, expect=DOCUMENT_TYPES)
    except Refused as exc:
        outcome = "skipped_robots" if exc.reason.startswith("robots") else "skipped_unsafe"
        return ItemOutcome(url, outcome, exc.error_class.value, exc.reason)
    except RequestRefused as exc:
        raise _StopRun(_failed(url, exc)) from None
    except IngestError as exc:
        if exc.error_class is ErrorClass.BLOCKED:
            raise _StopRun(_failed(url, exc)) from None
        return _failed(url, exc)
    if normalise_url(fetched.url) != normalise_url(url):
        # Redirected somewhere else (a withdrawn report's section index, a "moved" page): that page is
        # not this document, so it must never become its current version.
        return ItemOutcome(
            url, "failed", ErrorClass.UNEXPECTED.value, "redirected to a different page"
        )
    previous = None
    if existing is not None and (cur := store.current_version(conn, existing["id"])) is not None:
        previous = PreviousVersion(cur["char_count"], cur["text_sha256"])
    try:
        extracted = _extract(fetched, limits or ExtractionLimits())
        warnings = validate_document(inst, extracted, previous=previous)
    except IngestError as exc:
        if exc.error_class is ErrorClass.BLOCKED and str(exc) == "challenge_page":
            raise _StopRun(_failed(url, exc)) from None
        return _failed(url, exc)
    except Exception as exc:  # a parser bug on hostile input fails this document, not the run
        log.exception("extracting %s failed", url)
        return _failed(url, exc)
    published, date_warnings = _published(inst, extracted.published_hint, candidate, now_fn())
    warnings += date_warnings
    try:
        return _store(conn, inst, inst_id, candidate, doc_key, fetched, extracted, published,
                      tuple(warnings), artifacts, now_fn())  # fmt: skip
    except Exception as exc:  # the transaction rolled back; the previous version is still current
        log.exception("storing %s failed", url)
        return _failed(url, exc)


def _extract(fetched: FetchResult, limits: ExtractionLimits) -> Extracted:
    ctype = fetched.content_type.lower()
    if "pdf" in ctype or (
        ctype.startswith("application/octet-stream") and fetched.body[:5] == b"%PDF-"
    ):
        return extract_pdf(fetched.body, limits)
    if "html" in ctype:
        return extract_html(fetched.body, fetched.content_type, limits)
    raise IngestError(ErrorClass.LAYOUT_CHANGED, "unsupported content type")


def _title(*options: str | None, url: str) -> str:
    for option in options:
        if option:
            return option
    return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1] or url


def _published(
    inst: Institution, page_hint: str | None, candidate: Candidate, now: datetime
) -> tuple[PublishedDate | None, list[str]]:
    """The page's own date wins, then the file-name date, then the listing/feed date."""
    warnings: list[str] = []
    found: list[PublishedDate] = []
    sources = (
        ("page", page_hint and (lambda: parse_published(page_hint, now=now))),
        ("url", inst.url_date_regex and (lambda: date_from_url(
            candidate.url, inst.url_date_regex, inst.url_date_format or "", now=now))),
        ("listing", candidate.published_hint and (
            lambda: parse_published(candidate.published_hint or "", now=now))),
    )  # fmt: skip
    for name, parse in sources:
        if not parse:
            continue
        try:
            value = parse()
        except DateParseError:
            warnings.append(f"unparsed_{name}_date")
            continue
        if value is not None:
            found.append(value)
    if not found:
        return None, [*warnings, "no_publication_date"]
    chosen = found[0]
    for other in found[1:]:
        if _disagree(chosen, other):
            warnings.append("date_sources_disagree")
            break
    return chosen, warnings


def _disagree(a: PublishedDate, b: PublishedDate) -> bool:
    if "month" in (a.precision, b.precision):
        return (a.on.year, a.on.month) != (b.on.year, b.on.month)
    return abs((a.on - b.on).days) > 1


def _date_fields(published: PublishedDate | None) -> dict:
    if published is None:
        return {"published_on": None, "published_at": None, "precision": None}
    return {
        "published_on": published.on.isoformat(),
        "published_at": to_utc_iso(published.at) if published.at else None,
        "precision": published.precision,
    }


def _link_only(
    conn: sqlite3.Connection,
    inst: Institution,
    inst_id: int,
    candidate: Candidate,
    doc_key: str,
    known: bool,
    now: datetime,
) -> ItemOutcome:
    published, warnings = _published(inst, None, candidate, now)
    with transaction(conn):
        pub_id, _ = store.upsert_publication(
            conn, inst_id, doc_key=doc_key, url=candidate.url,
            title=_title(candidate.title, url=candidate.url), series=candidate.series,
            categories=inst.categories, content_status="link_only", now=now,
            **_date_fields(published),
        )  # fmt: skip
    outcome = "unchanged" if known else "link_only"
    return ItemOutcome(candidate.url, outcome, publication_id=pub_id, warnings=tuple(warnings))


def _store(
    conn: sqlite3.Connection,
    inst: Institution,
    inst_id: int,
    candidate: Candidate,
    doc_key: str,
    fetched: FetchResult,
    extracted: Extracted,
    published: PublishedDate | None,
    warnings: tuple[str, ...],
    artifacts: ArtifactStore | None,
    now: datetime,
) -> ItemOutcome:
    raw = artifacts.save(fetched) if artifacts is not None else None  # content-addressed file
    with transaction(conn):
        pub_id, created = store.upsert_publication(
            conn, inst_id, doc_key=doc_key, url=candidate.url,
            title=_title(extracted.title, candidate.title, url=candidate.url),
            series=candidate.series, categories=inst.categories, content_status="link_only",
            now=now, **_date_fields(published),
        )  # fmt: skip
        if store.current_version(conn, pub_id) is None:
            original = store.find_text_elsewhere(
                conn, extracted.text_sha256, exclude_publication_id=pub_id
            )
            if original is not None:
                store.mark_duplicate(conn, pub_id, original)
                return ItemOutcome(candidate.url, "duplicate", publication_id=pub_id,
                                   warnings=warnings)  # fmt: skip
        version_id, change = store.add_version(
            conn, pub_id, content_sha256=hashlib.sha256(fetched.body).hexdigest(), text_sha256=extracted.text_sha256,
            fmt=extracted.format, fetched_at=fetched.fetched_at,
            extractor_version=extracted.extractor_version,
            raw_artifact_id=record_artifact(conn, raw) if raw is not None else None,
            title=_title(extracted.title, candidate.title, url=candidate.url),
            sections=[store.SectionRow(s.ordinal, s.heading, s.text, s.page_start, s.page_end,
                                       s.char_start, s.char_end) for s in extracted.sections],
            page_count=extracted.page_count,
            licence_snapshot=json.dumps(inst.licence_snapshot(), sort_keys=True), now=now,
        )  # fmt: skip
    outcome = {"new": "new" if created else "updated"}.get(change, change)
    return ItemOutcome(candidate.url, outcome, publication_id=pub_id, version_id=version_id,
                       warnings=warnings)  # fmt: skip


def _outcome(result: RunResult, blocked: bool) -> str:
    failed = sum(1 for i in result.items if i.outcome == "failed")
    if blocked:
        return "blocked"
    if result.discovery_errors and not result.candidates:
        return "failed"
    if failed and failed == len(result.items):
        return "failed"
    if failed or result.discovery_errors:
        return "partial"
    return "ok"


_HEALTH = {"ok": "ok", "partial": "degraded", "failed": "failing", "blocked": "blocked"}


def _record(
    conn: sqlite3.Connection, inst_id: int, result: RunResult, started: datetime, finished: datetime
) -> None:
    problem = {"blocked": "blocked", "failed": "documents_or_discovery_failed",
               "partial": "some_documents_failed"}.get(result.outcome)  # fmt: skip
    with transaction(conn):
        run_id = store.record_run(
            conn, inst_id, started_at=started, finished_at=finished, outcome=result.outcome,
            dry_run=False, counts=result.counts, error_class=problem and result.outcome,
            detail=problem,
        )  # fmt: skip
        for item in result.items:
            detail = item.detail or (",".join(item.warnings) if item.warnings else None)
            store.record_item(
                conn, run_id, url=item.url, outcome=item.outcome, error_class=item.error_class,
                detail=detail, publication_id=item.publication_id, version_id=item.version_id,
            )  # fmt: skip
        store.set_health(conn, inst_id, state=_HEALTH[result.outcome], now=finished,
                         success=result.outcome == "ok", detail=problem)  # fmt: skip
