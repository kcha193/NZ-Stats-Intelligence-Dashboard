"""Internal draft routes: read-only, loopback binds only. `nzstats serve` mounts them with `--internal-drafts`, or
without a flag when the owner's list sets `auto_display` (Phase 4AA); `--no-internal-drafts` keeps them off.

Requests must come from the local dashboard, with the same checks as the private preview. Every item comes from
`drafts.draft_summaries`, the one draft gate, re-checked on each request over a read-only connection. An unreadable
registry or a malformed list shows nothing. Responses are not cached or indexed.

The models are an allowlist: raw model output, parameters, usage, cost and the owner's note have no field.
The derived presentation assessment exposes only output/evidence hashes for local audit traceability.
Each item states that it may have failed the checks and has no approval, so it can never read as a verified summary.
The feed also lists the reports held (`drafts.stored_reports`), by title, date and address only, and an item says when
a newer report from its institution is held. A newer report that is undated or withheld gives no notice.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path as FilePath
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from nzstats.clock import to_akl_iso
from nzstats.research.api import _is_loopback
from nzstats.research.assessment import PRESENTATION_VERIFIER, SCHEMA_VERSION, assess
from nzstats.research.bank_api import bank_router
from nzstats.research.banks import ADAPTERS, BankAdapter
from nzstats.research.drafts import (
    ALLOWLIST_FILE,
    ClaimStatus,
    DraftAllowlistError,
    DraftSummary,
    StoredReport,
    ValidationCategory,
    _civil_date,
    claim_paths,
    draft_summaries,
    load_allowlist,
    stored_reports,
)
from nzstats.research.private import PrivateSummary
from nzstats.research.private_api import (
    _HEADERS,
    Conn,
    PrivateBlockOut,
    PrivateDocumentOut,
    _blocks,
    _Out,
    _refuse_unless_local_dashboard,
)
from nzstats.research.registry import Institution, RegistryError, load_registry
from nzstats.research.verify import SCOPE, resolve_verifier

log = logging.getLogger(__name__)
# Phase 4T: the persistent notice, shown wherever a draft is. Its wording is fixed by the owner's brief.
# Phase 4AA: reworded by the owner for internal use.
NOTICE = (
    "AI-generated analysis for internal use. Claims are checked automatically against source documents but may"
    " contain errors. Not independently reviewed."
)
DRAFT_LABEL = (
    f"{NOTICE} It may have failed the automated checks and no person has approved it. Treat every line as"
    " unconfirmed. Not an official statistic."
)
RegistryLoader = Callable[[], Mapping[str, Institution]]


class DraftProblemOut(_Out):
    code: str
    severity: Literal["error", "warning"]
    message: str


class DraftClaimOut(PrivateBlockOut):
    path: str
    status: ClaimStatus
    problems: list[DraftProblemOut]


class DraftCountsOut(_Out):
    clean: int
    warning: int
    failed: int


class DraftAssessmentOut(_Out):
    schema_version: Literal["presentation-1"] = SCHEMA_VERSION
    id: str
    assessed_at: str
    verifier_version: str = PRESENTATION_VERIFIER
    original_verifier_version: str
    original_output_hash: str
    original_status: str
    evidence_hash: str
    errors: int
    warnings: int
    counts: DraftCountsOut
    claims: list[DraftClaimOut]
    executive_paths: list[str]
    warning_paths: list[str]
    excluded_paths: list[str]


class DraftProvenanceOut(_Out):
    provider: str
    model: str
    hosted: bool
    prompt_version: str
    processing_version: str
    verifier_version: str
    written_at: str
    checks_scope: str = SCOPE


class NewerReportOut(_Out):
    title: str
    published_on: date


class DraftItemOut(_Out):
    id: int
    label: str = DRAFT_LABEL
    official_statistic: Literal[False] = False
    approved_for_publication: Literal[False] = False
    human_reviewed: bool
    checks_passed: bool
    validation: ValidationCategory
    errors: int
    warnings: int
    counts: DraftCountsOut
    institution: str
    institution_name: str
    document: PrivateDocumentOut
    document_date: (
        str | None
    )  # the date or period the document states for itself; None when it states none
    licence: str
    licence_url: str | None
    provenance: DraftProvenanceOut
    claims: list[DraftClaimOut]
    assessment: DraftAssessmentOut | None
    newer_report: NewerReportOut | None


class StoredReportOut(_Out):
    institution: str
    institution_name: str
    title: str
    url: str
    series: str | None
    published_on: date | None
    newest: bool
    draft_id: int | None
    validation: (
        ValidationCategory | None
    )  # its draft's category, "unusable_response", or None (no attempt)
    withheld: bool = False  # Phase 4AA: a parsed summary exists but the draft gate shows none of it


class DraftFeedOut(_Out):
    mode: Literal["named", "automatic"]
    items: list[DraftItemOut]
    reports: list[StoredReportOut]
    notice: str = NOTICE


def _claims(d: DraftSummary) -> list[DraftClaimOut]:
    blocks = _blocks(PrivateSummary(d.id, d.institution, d.summary, d.warnings, d.row))
    return [
        DraftClaimOut(
            **block.model_dump(),
            path=path,
            status=claim.status,
            problems=[
                DraftProblemOut(code=p.code, severity=p.severity, message=p.message)
                for p in claim.problems
            ],
        )
        for block, path, claim in zip(blocks, claim_paths(d.summary), d.claims, strict=True)
    ]


def _newer_report(d: DraftSummary, reports: list[StoredReport]) -> NewerReportOut | None:
    """The institution's newest report when it was published after the one this draft covers."""
    published = _civil_date(d.row["published_on"])
    if published is None:
        return None
    for report in reports:
        if (
            report.newest
            and report.institution.key == d.institution.key
            and report.published_on is not None
            and report.published_on > published
        ):
            return NewerReportOut(title=report.title, published_on=report.published_on)
    return None


def _assessment(conn: sqlite3.Connection, d: DraftSummary) -> DraftAssessmentOut | None:
    result = assess(conn, d)
    if result is None:
        return None
    claims = _claims(result.draft)
    return DraftAssessmentOut(
        id=result.id,
        assessed_at=result.assessed_at,
        original_output_hash=result.original_output_hash,
        original_verifier_version=d.row["verifier_version"] or "",
        original_status=d.row["status"],
        evidence_hash=result.evidence_hash,
        errors=result.errors,
        warnings=result.draft.warnings,
        counts=DraftCountsOut(**result.draft.counts),
        claims=claims,
        executive_paths=[c.path for c in claims if c.status != "failed"],
        warning_paths=[c.path for c in claims if c.status == "warning"],
        excluded_paths=[c.path for c in claims if c.status == "failed"],
    )


def _item(d: DraftSummary, reports: list[StoredReport], conn: sqlite3.Connection) -> DraftItemOut:
    r, inst = d.row, d.institution
    errors = sum(p.severity == "error" for c in d.claims for p in c.problems)
    return DraftItemOut(
        id=d.id, human_reviewed=r["review_status"] == "approved", checks_passed=d.passed,
        validation=d.category, errors=errors, document_date=r["reference_period"],
        warnings=d.warnings, counts=DraftCountsOut(**d.counts), institution=inst.key, institution_name=inst.name,
        document=PrivateDocumentOut(title=r["title"], url=r["canonical_url"], published_on=r["published_on"],
                                    fetched_at=to_akl_iso(r["fetched_at"]), version_no=r["version_no"],
                                    format=r["format"], page_count=r["page_count"]),
        licence=inst.licence, licence_url=inst.licence_url,
        provenance=DraftProvenanceOut(provider=r["provider"], model=r["model"], hosted=bool(r["hosted"]),
                                      prompt_version=r["prompt_version"], processing_version=r["processing_version"],
                                      verifier_version=resolve_verifier(r["verifier_version"]), written_at=to_akl_iso(r["created_at"])),
        claims=_claims(d), assessment=_assessment(conn, d), newer_report=_newer_report(d, reports),
    )  # fmt: skip


def _report(report: StoredReport, drafts: list[DraftSummary]) -> StoredReportOut:
    draft = next((d for d in drafts if d.row["publication_id"] == report.publication_id), None)
    validation: ValidationCategory | None = (
        draft.category if draft else "unusable_response" if report.unusable_attempts else None
    )
    return StoredReportOut(
        institution=report.institution.key, institution_name=report.institution.name, title=report.title,
        url=report.url, series=report.series, published_on=report.published_on, newest=report.newest,
        draft_id=draft.id if draft else None, validation=validation,
        withheld=draft is None and report.usable_attempts > 0,
    )  # fmt: skip


def draft_bind_refusal(host: str) -> str | None:
    """Why `nzstats serve --internal-drafts` may not listen on `host`, or None. Loopback only, with no override."""
    if _is_loopback(host):
        return None
    return (
        f"refusing to serve internal drafts on {host!r}: they are for this machine only and have no login."
        " Listen on 127.0.0.1 (`nzstats serve --host 127.0.0.1 --internal-drafts`)"
    )


def owner_opted_in(data_dir: FilePath) -> bool:
    """Whether the owner's list explicitly sets `auto_display` (Phase 4AA: what a normal loopback start follows).

    A missing file, a named list without `auto_display`, or a malformed file is not an opt-in. This only decides
    whether the gate is mounted; every summary still passes `drafts.draft_summaries` on each request.
    """
    try:
        return load_allowlist(data_dir / ALLOWLIST_FILE).auto
    except DraftAllowlistError:
        log.warning("internal drafts stay off: the owner's internal draft list is not valid")
        return False


def internal_drafts_router(
    *,
    enabled: bool = False,
    registry: RegistryLoader | None = None,
    bank_adapters: Mapping[str, BankAdapter] = ADAPTERS,
) -> APIRouter:
    """The draft routes; off unless `enabled` (the CLI passes `--internal-drafts`). The bank-intelligence routes
    (Phase 4AE) are mounted here and nowhere else, behind this same gate."""
    load = registry or load_registry
    router = APIRouter()

    def gate(request: Request) -> None:
        if not enabled:
            raise HTTPException(404, "not found")
        _refuse_unless_local_dashboard(request)

    router.include_router(bank_router(gate=gate, load=load, adapters=bank_adapters))

    def read(request: Request, c: sqlite3.Connection) -> DraftFeedOut:
        path = request.app.state.settings.db_path.parent / ALLOWLIST_FILE
        try:
            reg = load()
            allowlist = load_allowlist(path)
        except (RegistryError, DraftAllowlistError, OSError) as exc:
            log.warning("internal drafts show nothing: %s", exc)
            return DraftFeedOut(mode="named", items=[], reports=[])
        drafts = draft_summaries(c, reg, allowlist)
        reports = stored_reports(c, reg)
        return DraftFeedOut(mode="automatic" if allowlist.auto else "named",
                            items=[_item(d, reports, c) for d in drafts],
                            reports=[_report(r, drafts) for r in reports])  # fmt: skip

    deps = [Depends(gate)]

    @router.get("/internal/drafts", response_model=DraftFeedOut, dependencies=deps)
    def feed(request: Request, c: Conn, response: Response) -> DraftFeedOut:
        response.headers.update(_HEADERS)
        return read(request, c)

    @router.get("/internal/drafts/{summary_id}", response_model=DraftItemOut, dependencies=deps)
    def detail(
        request: Request,
        c: Conn,
        response: Response,
        summary_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    ) -> DraftItemOut:
        found = next((i for i in read(request, c).items if i.id == summary_id), None)
        if found is None:
            raise HTTPException(404, "not found")
        response.headers.update(_HEADERS)
        return found

    return router
