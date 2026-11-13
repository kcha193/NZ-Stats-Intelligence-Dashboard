"""Read the figures out of a stored PDF version (Phase 4AF). Local and offline: it never fetches and calls no model.

It needs only what holding and showing the document already needs (the route the version came in by is still
permitted, and the content policy allows full text), because it adds no processing destination: the bytes are the
copy already stored, parsed on this machine. A source that may not be held, or shown, yields nothing. Every refusal is
fixed wording. Re-running on the same document and interpreter is a no-op.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from nzstats.domain import IngestError
from nzstats.research.extract import ExtractionLimits
from nzstats.research.registry import ContentPolicy, Institution
from nzstats.research.table_forecast import interpret
from nzstats.research.table_grid import find_tables
from nzstats.research.table_store import store_extraction
from nzstats.research.table_words import extract_words, words_sha256
from nzstats.sources.artifacts import ArtifactStore, valid_rel

log = logging.getLogger(__name__)

_VERSION = (
    "SELECT v.id, v.title, p.canonical_url, v.format, v.purged_at, v.acquisition, i.key, a.path, a.sha256 AS raw_sha256"
    " FROM research_document_version v JOIN research_publication p ON p.id = v.publication_id"
    " JOIN research_institution i ON i.id = p.institution_id"
    " LEFT JOIN raw_artifact a ON a.id = v.raw_artifact_id WHERE v.id = ?"
)


@dataclass(frozen=True)
class TableIngestResult:
    status: Literal["stored", "unchanged", "dry_run", "refused"]
    reason: str | None = None
    forecasts: int = 0
    rejections: int = 0
    # How many rejections of each fixed code, sorted by code: content-free, so a dry run can say why tables gave nothing.
    rejection_codes: tuple[tuple[str, int], ...] = ()


def _refused(reason: str) -> TableIngestResult:
    return TableIngestResult("refused", reason)


def version_refusal(
    row: sqlite3.Row | None, registry: Mapping[str, Institution]
) -> tuple[str | None, Institution | None]:
    """(why this version's table figures may not be read or shown, the institution); (None, inst) when they may."""
    if row is None:
        return "unknown version", None
    if row["purged_at"]:
        return "purged", None
    inst = registry.get(row["key"])
    if inst is None:
        return "unknown institution", None
    if not inst.holds(row["acquisition"]):
        return "source not permitted", inst
    if inst.content_policy is not ContentPolicy.FULL_TEXT:
        return "content policy does not allow full text", inst
    return None, inst


def extract_version_tables(
    conn: sqlite3.Connection,
    version_id: int,
    artifacts: ArtifactStore,
    registry: Mapping[str, Institution],
    now: datetime,
    *,
    dry_run: bool = False,
    isolate: bool | None = None,
) -> TableIngestResult:
    row = conn.execute(_VERSION, (version_id,)).fetchone()
    reason, inst = version_refusal(row, registry)
    if reason or inst is None:
        return _refused(reason or "unknown institution")
    if row["format"] != "pdf":
        return _refused("not a pdf")
    if not row["path"] or not valid_rel(row["path"]) or not artifacts.exists(row["path"]):
        return _refused("raw copy unavailable")
    body = (artifacts.root / row["path"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
        return _refused("raw copy does not match the stored version")
    try:
        words = extract_words(body, ExtractionLimits(), isolate=isolate)
    except IngestError as exc:
        log.warning(
            "table extraction refused for version %s: %s", version_id, exc.error_class.value
        )
        return _refused(f"pdf could not be read ({exc})")
    tables, grid_rejections = find_tables(words)
    names = (inst.name, inst.key, inst.name.removesuffix(" New Zealand"))
    # Ingestion uses the URL basename when neither metadata nor the owner names
    # a document. That generated fallback is not a statement about its scope.
    fallback = (
        urlsplit(row["canonical_url"]).path.rstrip("/").rsplit("/", 1)[-1] or row["canonical_url"]
    )
    title = row["title"] if row["title"] != fallback else ""
    forecasts, rejections = interpret(tables, publisher_names=names, document_title=title)
    rejections = (*grid_rejections, *rejections)
    codes = tuple(sorted(Counter(r.code for r in rejections).items()))
    if dry_run:
        return TableIngestResult("dry_run", None, len(forecasts), len(rejections), codes)
    try:
        stored = store_extraction(
            conn, version_id, now, forecasts, rejections, words_sha256=words_sha256(words)
        )
    except sqlite3.IntegrityError:
        # The only refusal the schema makes here is a purge that landed while the (slow) parse ran.
        log.warning("table figures for version %s were refused by the store", version_id)
        return _refused("purged")
    status = "stored" if stored is not None else "unchanged"
    return TableIngestResult(status, None, len(forecasts), len(rejections), codes)
