"""Permission-compliant manual import of an owner-supplied document (Phase 3E).

For a source whose terms (read directly) permit storing a copy, but whose site refuses automated access, a person
can obtain the document in a browser and import the file here. Possession of a file is not permission: the import is
refused unless the registry records a separate `manual_import = "approved"` decision, and it never grants or uses
automated access. Nothing is requested: the document's address is checked against the institution's URL policy
(https, allowed host and path, no blocked prefix) without a DNS lookup, so only approved source URLs are recorded.

The file goes through the crawler's extraction and validation (access walls, challenge pages, minimum length, the
shrink guard) and its store: content-addressed raw bytes, a version per distinct text (a revert reuses the old one),
sections with offsets and pages. Each import that reaches the store writes an append-only audit record (who, when,
hashes, outcome, the registry permissions in force, a private note) in the same transaction. LLM processing, public
display, review and publication remain separate gates, exactly as for crawled documents.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from nzstats.clock import to_utc_iso
from nzstats.domain import IngestError
from nzstats.research import store
from nzstats.research.dates import DateParseError, PublishedDate, parse_published
from nzstats.research.discover import Candidate
from nzstats.research.extract import Extracted, ExtractionLimits
from nzstats.research.extract_html import extract_html
from nzstats.research.extract_pdf import extract_pdf
from nzstats.research.fetch import DEFAULT_MAX_BYTES
from nzstats.research.ingest import ItemOutcome, store_document
from nzstats.research.registry import Institution
from nzstats.research.safety import HostPolicy, UnsafeUrl
from nzstats.research.validate import PreviousVersion, safe_detail, validate_document
from nzstats.sources.artifacts import ArtifactStore
from nzstats.sources.fetcher import FetchResult
from nzstats.store.db import transaction

log = logging.getLogger(__name__)
FORMATS = {"html": "text/html; charset=utf-8", "pdf": "application/pdf"}


class ImportRefused(ValueError):
    """The import was refused before anything was written; the message is fixed wording, safe to print."""


@dataclass(frozen=True)
class ImportResult:
    institution: str
    url: str
    outcome: str  # new|updated|reactivated|unchanged|duplicate
    publication_id: int | None
    version_id: int | None
    content_sha256: str
    warnings: tuple[str, ...] = ()


def check_address(inst: Institution, url: str) -> str:
    """The normalised document address if it is on the institution's URL policy; no DNS lookup, no request."""
    policy = HostPolicy(inst.allowed_hosts, allowed_path_prefixes=inst.allowed_path_prefixes,
                        blocked_path_prefixes=inst.blocked_path_prefixes, resolver=None)  # fmt: skip
    try:
        return policy.check(url or "")
    except (UnsafeUrl, ValueError) as exc:
        raise ImportRefused(f"the document address is not allowed for {inst.key} ({exc})") from None


def _extract(body: bytes, file_format: str, limits: ExtractionLimits) -> Extracted:
    if file_format == "pdf":
        if body[:5] != b"%PDF-":
            raise ImportRefused("the file is not a PDF")
        return extract_pdf(body, limits)
    return extract_html(body, FORMATS["html"], limits)


def _published(
    published_on: date | None, extracted: Extracted, now: datetime
) -> PublishedDate | None:
    """The date the importer states wins; otherwise the page's own date; never a guess."""
    if published_on is not None:
        return PublishedDate(published_on, None, "day")
    if extracted.published_hint:
        try:
            return parse_published(extracted.published_hint, now=now)
        except DateParseError:
            return None
    return None


def import_document(
    conn: sqlite3.Connection,
    inst: Institution,
    *,
    body: bytes,
    file_format: str,
    url: str,
    importer: str,
    note: str,
    now: datetime,
    artifacts: ArtifactStore | None,
    title: str | None = None,
    published_on: date | None = None,
    series: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    limits: ExtractionLimits | None = None,
) -> ImportResult:
    """Store an owner-supplied copy of one document, or raise `ImportRefused` having written nothing."""
    refusal = inst.import_refusal()
    if refusal is not None:
        raise ImportRefused(refusal)
    if not importer or not importer.strip():
        raise ImportRefused("a named importer is required")
    if not note or not note.strip():
        raise ImportRefused("a note is required (where and how the copy was obtained)")
    if file_format not in FORMATS:
        raise ImportRefused(f"unsupported format {file_format!r} (html or pdf)")
    if len(body) > max_bytes:
        raise ImportRefused(f"the file is larger than {max_bytes} bytes")
    address = check_address(inst, url)
    try:
        extracted = _extract(body, file_format, limits or ExtractionLimits())
    except ImportRefused:
        raise
    except IngestError as exc:
        raise ImportRefused(f"extraction failed: {safe_detail(exc)}") from None
    except (
        Exception
    ) as exc:  # a parser bug on a hostile file refuses the import; the message is logged only
        log.exception("extracting an imported %s file failed", file_format)
        raise ImportRefused(f"extraction failed: {safe_detail(exc)}") from None
    doc_key = f"{inst.key}:{address.split('://', 1)[1]}"
    existing = conn.execute("SELECT current_version_id FROM research_publication WHERE doc_key=?",
                            (doc_key,)).fetchone()  # fmt: skip
    previous = None
    if existing is not None and existing[0] is not None:
        row = conn.execute("SELECT char_count, text_sha256 FROM research_document_version WHERE id=?",
                           (existing[0],)).fetchone()  # fmt: skip
        previous = PreviousVersion(row["char_count"], row["text_sha256"])
    try:
        warnings = validate_document(inst, extracted, previous=previous)
    except IngestError as exc:
        raise ImportRefused(f"validation failed: {safe_detail(exc)}") from None
    content_sha = hashlib.sha256(body).hexdigest()
    snapshot = json.dumps(inst.licence_snapshot(), sort_keys=True)
    with transaction(conn):
        inst_id = store.upsert_institution(conn, key=inst.key, name=inst.name,
                                           review_status=inst.review_status.value,
                                           content_policy=inst.content_policy.value, now=now)  # fmt: skip

    def audit(item: ItemOutcome) -> None:
        conn.execute(
            "INSERT INTO research_manual_import(institution_id, url, publication_id, version_id, outcome,"
            " file_format, content_sha256, text_sha256, imported_by, note, licence_snapshot, imported_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (inst_id, address, item.publication_id, item.version_id, item.outcome, file_format, content_sha,
             extracted.text_sha256, importer.strip(), note.strip(), snapshot, to_utc_iso(now)),
        )  # fmt: skip

    if store.purged_text(conn, inst_id, extracted.text_sha256) is not None:
        raise ImportRefused(
            "this text was purged and cannot be stored again (see `research purge`)"
        )
    fetched = FetchResult(
        address, 0, FORMATS[file_format], body, now
    )  # status 0: not fetched over HTTP
    item = store_document(
        conn, inst, inst_id, Candidate(address, title=title, series=series), doc_key, fetched, extracted,
        _published(published_on, extracted, now), tuple(warnings), artifacts, now, acquisition="manual",
        audit=audit,
    )  # fmt: skip
    warnings = item.warnings
    if item.version_id is not None and item.outcome in ("unchanged", "reactivated"):
        route = conn.execute("SELECT acquisition FROM research_document_version WHERE id=?",
                             (item.version_id,)).fetchone()[0]  # fmt: skip
        if (
            route != "manual"
        ):  # the same text was first stored by the crawler: it stays under that approval
            warnings = (*warnings, "stored_by_crawler")
    return ImportResult(inst.key, address, item.outcome, item.publication_id, item.version_id, content_sha,
                        warnings)  # fmt: skip
