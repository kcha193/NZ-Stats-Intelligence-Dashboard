"""Table-derived figures as bank forecasts (Phase 4AF): gated like the drafts, reconciled, evidence kept.

A stored table figure reaches the bank analytics only when everything the internal draft gate asks of an institution
and a document also holds here: the owner's automatic mode is on, the document is the current held copy of a bank
that is still permitted by the route it came in by, its content policy allows full text and its address is on an
allowed host. The figure must be a forecast (not an actual), have a number (a dash stays missing), and be the bank's
own (a "Source:" line naming someone else makes it a third party's).

Reconciliation against the bank's checked claims then decides, with fixed codes:
  * no counterpart                     -> used;
  * an exact match                     -> not added: the checked claim already states it, so it is one statement and is
                                          counted once (it is still reported as an exact match);
  * a different value                  -> used, so the analytics' own conflict rule leaves both out;
  * a rounding difference              -> the claim is kept and the table figure dropped (two precisions of one
                                          number would otherwise be a spurious conflict);
  * a unit, horizon or attribution difference, or no one-to-one match -> dropped; neither side is guessed.
Agreement of the two methods is never treated as proof of economic correctness.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from nzstats.research.api_models import EvidenceOut, ForecastOut, InstitutionOut
from nzstats.research.bank_forecast import (
    NormalizedForecast,
    adjustment_conflicts,
    canonical_label,
    derive_adjustment,
    derive_geography,
)
from nzstats.research.bank_view import ExcludedClaim
from nzstats.research.banks import ADAPTERS, BankAdapter, report_kind_of
from nzstats.research.drafts import DraftAllowlist
from nzstats.research.public import allowed_document_url
from nzstats.research.registry import ContentPolicy, Institution
from nzstats.research.table_context import evidence_texts, stored_context_rejection
from nzstats.research.table_forecast import INTERPRETER_VERSION
from nzstats.research.table_reconcile import Reconciliation, reconcile
from nzstats.research.table_store import (
    StoredTableForecast,
    latest_interpreter,
    load_forecasts,
    load_rejections,
)

_VERSIONS = (
    "SELECT e.id AS extraction_id, v.id AS version_id, v.title, v.acquisition, v.superseded_at, v.purged_at,"
    " p.canonical_url, p.published_on, p.current_version_id, p.duplicate_of_id, i.key AS institution"
    " FROM research_table_extraction e JOIN research_document_version v ON v.id = e.version_id"
    " JOIN research_publication p ON p.id = v.publication_id"
    " JOIN research_institution i ON i.id = p.institution_id"
    " WHERE e.id = (SELECT MAX(id) FROM research_table_extraction WHERE version_id = e.version_id)"
    " AND e.interpreter_version = ?"
    " ORDER BY v.id"
)
_QUOTE_MAX = 300
_UNRESOLVED = frozenset(
    {"units_mismatch", "horizon_mismatch", "attribution_mismatch", "ambiguous_or_unsupported"}
)


# Phase 4AH: every current, dated, shown bank report, to tell whether its figures were read (see `document_states`).
_CURRENT_DOCUMENTS = (
    "SELECT v.id AS version_id, v.title, v.acquisition, v.superseded_at, v.purged_at,"
    " p.canonical_url, p.published_on, p.current_version_id, p.duplicate_of_id, i.key AS institution"
    " FROM research_publication p JOIN research_document_version v ON v.id = p.current_version_id"
    " JOIN research_institution i ON i.id = p.institution_id"
    " WHERE p.published_on IS NOT NULL ORDER BY v.id"
)
# A refused scenario cell is known not to be a central figure; every other refusal could be any measure.
_SCENARIO_CODES = frozenset({"scenario_table", "scenario_row", "scenario_column"})
DocumentStateName = Literal["read", "incomplete", "incomplete_scenario", "not_read"]


@dataclass(frozen=True)
class DocumentState:
    """Whether a bank's dated quarterly outlook report was read. Content-free: a key, ids, a date and a state."""

    institution_key: str
    version_id: int
    published_on: str
    state: DocumentStateName


def _shown(row: sqlite3.Row, inst: Institution | None) -> bool:
    """The document-level conditions of the internal draft gate, for a document rather than a summary."""
    return (
        inst is not None
        and inst.kind == "bank"
        and not row["purged_at"]
        and row["current_version_id"] == row["version_id"]
        and not row["superseded_at"]
        and row["duplicate_of_id"] is None
        and inst.content_policy is ContentPolicy.FULL_TEXT
        and inst.holds(row["acquisition"])
        and allowed_document_url(row["canonical_url"], inst)
    )


def _quote(f: StoredTableForecast) -> str:
    e = f.evidence
    text = f"{e.get('row_label', '')} | {' / '.join(e.get('header_texts', []))} | {e.get('cell_text', '')} | {' / '.join(e.get('unit_texts', []))} | {e.get('caption') or ''} | {e.get('document_title') or ''} | {' / '.join(e.get('notes', []))}"
    return text[:_QUOTE_MAX]


def _normalized(
    f: StoredTableForecast, row: sqlite3.Row, inst: Institution, adapters: Mapping[str, BankAdapter]
) -> NormalizedForecast:
    assert f.value is not None
    context = " ".join((f.evidence.get("document_title") or "", *evidence_texts(f.evidence)))
    adjustment = derive_adjustment(f.label, context)
    label = canonical_label(f.label, adjustment)
    out = ForecastOut(
        summary_id=-f.extraction_id,  # negative: a table extraction, never a summary
        institution=InstitutionOut(key=inst.key, name=inst.name, kind=inst.kind),
        document_title=row["title"],
        published_on=row["published_on"],
        indicator=f.indicator,
        indicator_label=label,
        horizon=f.horizon,
        value=float(f.value),
        unit=f.unit,
        direction="unclear",
        scenario=None,
        qualification=None,
        evidence=[EvidenceOut(section_ordinal=-1, page=f.page, quote=_quote(f))],
    )
    return NormalizedForecast(
        forecast=out,
        institution_key=inst.key,
        document_version_id=f.version_id,
        claim_path=f"tables[{f.extraction_id}:{f.ordinal}]",
        report_kind=report_kind_of(inst.key, row["canonical_url"], row["title"], adapters),
        forecast_author=inst.name,
        geography=derive_geography(f.indicator, f.label, f.horizon, f.unit),
        measure=f.label,
        adjustment=adjustment,
        adjustment_conflict=adjustment_conflicts(f.label, context),
        extraction_method="table",
        verifier_version=f.interpreter_version,
        raw_value=float(f.value),
    )


def table_forecasts(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    claims: list[NormalizedForecast],
    allowlist: DraftAllowlist,
    adapters: Mapping[str, BankAdapter] = ADAPTERS,
) -> tuple[list[NormalizedForecast], list[ExcludedClaim], list[Reconciliation]]:
    """(usable figures, exclusions by fixed code, how each compares with the checked claims). Read-only."""
    if not allowlist.auto:  # the owner has not switched the automatic internal view on
        return [], [], []
    usable: list[NormalizedForecast] = []
    excluded: list[ExcludedClaim] = []
    recs: list[Reconciliation] = []
    for row in conn.execute(_VERSIONS, (INTERPRETER_VERSION,)).fetchall():
        inst = registry.get(row["institution"])
        if not _shown(row, inst):
            continue
        assert inst is not None
        stored = load_forecasts(conn, row["version_id"])
        mine = [c for c in claims if c.document_version_id == row["version_id"]]
        found = reconcile(stored, mine)
        recs.extend(found)
        cls_of = {tid: r.cls for r in found for tid in r.table_ids}
        by_id = {f.id: f for f in stored}
        conflicting_ids: set[int] = set()
        for r in found:
            figures = [by_id[tid] for tid in r.table_ids]
            if (
                r.note_code == "several_differing_readings"
                and len({f.value for f in figures}) > 1
                and len({f.unit for f in figures}) == 1
                and all(f.author_role == "author" for f in figures)
            ):
                conflicting_ids.update(r.table_ids)
        for f in stored:
            if f.kind != "forecast" or f.missing or f.value is None:
                continue
            path = f"tables[{f.extraction_id}:{f.ordinal}]"
            cls = cls_of.get(f.id, "no_counterpart")
            if cls == "exact_match":
                continue  # the checked claim already states it: one statement, counted once (see the module note)
            code = None
            if f.author_role == "third_party":
                code = "table_third_party"
            elif stored_context_rejection(f.label, f.evidence):
                code = "table_unresolved_reconciliation"
            elif cls == "rounding_difference":
                code = "reconciliation_rounding"
            elif cls in _UNRESOLVED and f.id not in conflicting_ids:
                code = "table_unresolved_reconciliation"
            if code is None:
                usable.append(_normalized(f, row, inst, adapters))
            else:
                excluded.append(ExcludedClaim(inst.key, -f.extraction_id, path, code, None))  # type: ignore[arg-type]
    return usable, excluded, recs


def _table_state(
    conn: sqlite3.Connection, version_id: int, *, summary_read: bool
) -> DocumentStateName | Literal["stale"] | None:
    """What the latest table extraction says about a report: None when there is none (or it read nothing usable),
    `stale` when it was made by an older interpreter (its tables must be read again). An admitted summary preserves
    scenario refusals even when no own table figures survive; refusals alone do not count as a reading."""
    interpreter = latest_interpreter(conn, version_id)
    if interpreter is None:
        return None  # never extracted, or refused by the reader (which stores nothing)
    if interpreter != INTERPRETER_VERSION:
        return "stale"
    codes = {r.code for r in load_rejections(conn, version_id)}
    own = [
        f
        for f in load_forecasts(conn, version_id)
        if f.kind == "forecast" and f.author_role == "author"
    ]
    if codes - _SCENARIO_CODES or any(f.missing for f in own):
        return "incomplete"  # a refused cell or a printed dash: which measure it was is not known, and not guessed
    if not own:
        return "incomplete_scenario" if codes and summary_read else None
    return "incomplete_scenario" if codes else "read"


def _identified(row: sqlite3.Row, inst: Institution | None) -> bool:
    """A bank's live, current, unique report, whether or not it may be shown."""
    return (
        inst is not None
        and inst.kind == "bank"
        and not row["purged_at"]
        and row["current_version_id"] == row["version_id"]
        and not row["superseded_at"]
        and row["duplicate_of_id"] is None
    )


def document_states(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    allowlist: DraftAllowlist,
    read_versions: set[int],
    adapters: Mapping[str, BankAdapter] = ADAPTERS,
) -> list[DocumentState]:
    """Each current, dated quarterly outlook report of a bank, and whether its figures were read. Read-only.

    `read_versions` are the versions with an admitted draft summary. A report is:
      * `incomplete` when its current table extraction refused a cell or printed an own forecast without a value (in
        either display mode: the refusal is a fact about the report);
      * `not_read` when it may not be shown (route, content policy or host), when its tables were read only by an
        older interpreter, or when nothing usable was read;
      * `incomplete_scenario` when only scenario cells were refused, `read` otherwise. Table figures count as read only
        in the owner's automatic mode, as for the figures themselves; without usable tables an admitted summary is the
        reading (Phase 4AE).
    Purged, superseded, duplicate and undated reports have no state.
    """
    out: list[DocumentState] = []
    for row in conn.execute(_CURRENT_DOCUMENTS).fetchall():
        inst = registry.get(row["institution"])
        if not _identified(row, inst):
            continue
        assert inst is not None
        if report_kind_of(inst.key, row["canonical_url"], row["title"], adapters) != "outlook":
            continue
        vid = int(row["version_id"])
        state: DocumentStateName
        if not _shown(
            row, inst
        ):  # checked first: an unshown report's tables are not read on every request
            out.append(DocumentState(inst.key, vid, row["published_on"], "not_read"))
            continue
        tables = _table_state(conn, vid, summary_read=vid in read_versions)
        if tables == "stale":
            state = "not_read"
        elif tables == "incomplete":
            state = "incomplete"
        elif tables is not None and allowlist.auto:
            state = tables
        elif vid in read_versions:
            state = "incomplete_scenario" if tables == "incomplete_scenario" else "read"
        else:
            state = "not_read"
        out.append(DocumentState(inst.key, vid, row["published_on"], state))
    return out
