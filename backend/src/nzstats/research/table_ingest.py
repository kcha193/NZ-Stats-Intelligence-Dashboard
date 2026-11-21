"""Read the figures out of a stored PDF version (Phase 4AF) or ANZ's forecasts workbook (Phase 4AP). Local and
offline: it never fetches and calls no model.

It needs only what holding and showing the document already needs (the route the version came in by is still
permitted, and the content policy allows full text), because it adds no processing destination: the bytes are the
copy already stored, parsed on this machine. A source that may not be held, or shown, yields nothing. Every refusal is
fixed wording. Re-running on the same document and interpreter is a no-op.

A workbook's figures are stored only with the owner's reconciliation: a dry run gives the candidates and an 8-character
code over exactly those candidates; the owner checks every one against the original workbook (in their own terminal)
and stores them with that code. A different code, or none, stores nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from nzstats.domain import IngestError
from nzstats.research.banks import ADAPTERS, BankAdapter
from nzstats.research.extract import ExtractionLimits
from nzstats.research.registry import ContentPolicy, Institution
from nzstats.research.table_forecast import TableForecast, interpret
from nzstats.research.table_grid import find_tables
from nzstats.research.table_store import store_extraction
from nzstats.research.table_words import extract_words, words_sha256
from nzstats.research.xlsx_anz import INTERPRETER_VERSION as XLSX_INTERPRETER
from nzstats.research.xlsx_anz import interpret_anz_workbook
from nzstats.research.xlsx_cells import cells_sha256, read_cells
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
    # Workbooks only: the reconciliation code over the candidates, and (dry run) the candidates for the owner's terminal.
    candidate_hash8: str | None = None
    candidates: tuple[TableForecast, ...] = ()


def _refused(reason: str) -> TableIngestResult:
    return TableIngestResult("refused", reason)


# The source and series whose workbook layout the one workbook interpreter was built for.
_WORKBOOK_SOURCE, _WORKBOOK_SERIES = "anz", "forecasts_workbook"


def candidate_hash8(forecasts: tuple[TableForecast, ...] | list[TableForecast]) -> str:
    """8 hex characters over every candidate's cell, identity, printed text and value: what the owner reconciles."""
    canonical = [
        [f.page, f.table, f.row, f.col, f.indicator, f.label, f.period_text, f.horizon, f.kind, f.unit, f.raw_text,
         None if f.value is None else str(f.value), f.missing, f.author_role, f.evidence.get("workbook_sha256")]
        for f in forecasts
    ]  # fmt: skip
    return hashlib.sha256(
        json.dumps([XLSX_INTERPRETER, canonical], ensure_ascii=False).encode()
    ).hexdigest()[:8]


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
    confirm: str | None = None,
    adapters: Mapping[str, BankAdapter] = ADAPTERS,
) -> TableIngestResult:
    row = conn.execute(_VERSION, (version_id,)).fetchone()
    reason, inst = version_refusal(row, registry)
    if reason or inst is None:
        return _refused(reason or "unknown institution")
    if row["format"] not in ("pdf", "xlsx"):
        return _refused("not a pdf or workbook")
    if row["format"] == "xlsx":
        adapter = adapters.get(inst.key) if inst.key == _WORKBOOK_SOURCE else None
        series = adapter.series_of(row["canonical_url"], "") if adapter else None
        if adapter is None:
            return _refused("no workbook interpreter for this source")
        if series is None or series.key != _WORKBOOK_SERIES:
            return _refused("not the ANZ forecasts workbook")
    if not row["path"] or not valid_rel(row["path"]) or not artifacts.exists(row["path"]):
        return _refused("raw copy unavailable")
    body = (artifacts.root / row["path"]).read_bytes()
    if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
        return _refused("raw copy does not match the stored version")
    if row["format"] == "xlsx":
        return _extract_workbook(conn, version_id, row, inst, body, now, dry_run=dry_run, isolate=isolate,
                                 confirm=confirm)  # fmt: skip
    try:
        words = extract_words(body, ExtractionLimits(), isolate=isolate)
    except IngestError as exc:
        log.warning(
            "table extraction refused for version %s: %s", version_id, exc.error_class.value
        )
        return _refused(f"pdf could not be read ({exc})")
    tables, grid_rejections = find_tables(words)
    names = (inst.name, inst.key, inst.name.removesuffix(" New Zealand"))
    forecasts, rejections = interpret(
        tables, publisher_names=names, document_title=_document_title(row)
    )
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


def _document_title(row: sqlite3.Row) -> str:
    # Ingestion uses the URL basename when neither metadata nor the owner names a document. That generated fallback
    # is not a statement about its scope.
    fallback = (
        urlsplit(row["canonical_url"]).path.rstrip("/").rsplit("/", 1)[-1] or row["canonical_url"]
    )
    return row["title"] if row["title"] != fallback else ""


def _extract_workbook(
    conn: sqlite3.Connection,
    version_id: int,
    row: sqlite3.Row,
    inst: Institution,
    body: bytes,
    now: datetime,
    *,
    dry_run: bool,
    isolate: bool | None,
    confirm: str | None,
) -> TableIngestResult:
    try:
        wb = read_cells(body, isolate=isolate)
    except IngestError as exc:
        log.warning(
            "workbook extraction refused for version %s: %s", version_id, exc.error_class.value
        )
        return _refused(f"workbook could not be read ({exc})")
    names = (inst.name, inst.key, inst.name.removesuffix(" New Zealand"))
    forecasts, rejections = interpret_anz_workbook(
        wb,
        publisher_names=names,
        document_title=_document_title(row),
        workbook_sha256=row["raw_sha256"],
    )
    codes = tuple(sorted(Counter(r.code for r in rejections).items()))
    code = candidate_hash8(forecasts)
    if dry_run:
        return TableIngestResult(
            "dry_run", None, len(forecasts), len(rejections), codes, code, forecasts
        )
    if confirm is None:
        return _refused(
            "owner reconciliation required: run --dry-run --list in your own terminal, then --confirm"
        )
    if confirm != code:
        return _refused("confirmation does not match the current candidates")
    try:
        stored = store_extraction(
            conn, version_id, now, forecasts, rejections, words_sha256=cells_sha256(wb),
            interpreter_version=XLSX_INTERPRETER,
        )  # fmt: skip
    except sqlite3.IntegrityError:
        log.warning("workbook figures for version %s were refused by the store", version_id)
        return _refused("purged")
    status = "stored" if stored is not None else "unchanged"
    return TableIngestResult(status, None, len(forecasts), len(rejections), codes, code)
