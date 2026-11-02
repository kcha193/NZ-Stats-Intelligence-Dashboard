"""Internal draft routes: read-only, mounted only by `nzstats serve --internal-drafts`, loopback binds only.

Requests must come from the local dashboard, with the same checks as the private preview. Every item comes from
`drafts.draft_summaries`, the one draft gate, re-checked on each request over a read-only connection. An unreadable
registry or a malformed list shows nothing. Responses are not cached or indexed.

The models are an allowlist: raw model output, hashes, parameters, usage, cost and the owner's note have no field.
Each item states that it may have failed the checks and has no approval, so it can never read as a verified summary.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Mapping
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from nzstats.clock import to_akl_iso
from nzstats.research.api import _is_loopback
from nzstats.research.drafts import (
    ALLOWLIST_FILE,
    ClaimStatus,
    DraftAllowlistError,
    DraftSummary,
    claim_paths,
    draft_summaries,
    load_allowlist,
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
from nzstats.research.verify import SCOPE, VERIFIER_VERSION

log = logging.getLogger(__name__)
DRAFT_LABEL = (
    "Internal draft. AI summary of institutional commentary that may have failed the automated checks, and no person"
    " has approved it. Treat every line as unconfirmed. Not an official statistic."
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


class DraftProvenanceOut(_Out):
    provider: str
    model: str
    hosted: bool
    prompt_version: str
    processing_version: str
    verifier_version: str
    written_at: str
    checks_scope: str = SCOPE


class DraftItemOut(_Out):
    id: int
    label: str = DRAFT_LABEL
    official_statistic: Literal[False] = False
    approved_for_publication: Literal[False] = False
    human_reviewed: bool
    checks_passed: bool
    errors: int
    warnings: int
    counts: DraftCountsOut
    institution: str
    institution_name: str
    document: PrivateDocumentOut
    licence: str
    licence_url: str | None
    provenance: DraftProvenanceOut
    claims: list[DraftClaimOut]


class DraftFeedOut(_Out):
    items: list[DraftItemOut]
    notice: str = DRAFT_LABEL


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


def _item(d: DraftSummary) -> DraftItemOut:
    r, inst = d.row, d.institution
    errors = sum(p.severity == "error" for c in d.claims for p in c.problems)
    return DraftItemOut(
        id=d.id, human_reviewed=r["review_status"] == "approved", checks_passed=d.passed, errors=errors,
        warnings=d.warnings, counts=DraftCountsOut(**d.counts), institution=inst.key, institution_name=inst.name,
        document=PrivateDocumentOut(title=r["title"], url=r["canonical_url"], published_on=r["published_on"],
                                    fetched_at=to_akl_iso(r["fetched_at"]), version_no=r["version_no"],
                                    format=r["format"], page_count=r["page_count"]),
        licence=inst.licence, licence_url=inst.licence_url,
        provenance=DraftProvenanceOut(provider=r["provider"], model=r["model"], hosted=bool(r["hosted"]),
                                      prompt_version=r["prompt_version"], processing_version=r["processing_version"],
                                      verifier_version=VERIFIER_VERSION, written_at=to_akl_iso(r["created_at"])),
        claims=_claims(d),
    )  # fmt: skip


def draft_bind_refusal(host: str) -> str | None:
    """Why `nzstats serve --internal-drafts` may not listen on `host`, or None. Loopback only, with no override."""
    if _is_loopback(host):
        return None
    return (
        f"refusing to serve internal drafts on {host!r}: they are for this machine only and have no login."
        " Listen on 127.0.0.1 (`nzstats serve --host 127.0.0.1 --internal-drafts`)"
    )


def internal_drafts_router(
    *, enabled: bool = False, registry: RegistryLoader | None = None
) -> APIRouter:
    """The draft routes; off unless `enabled` (the CLI passes `--internal-drafts`)."""
    load = registry or load_registry
    router = APIRouter()

    def gate(request: Request) -> None:
        if not enabled:
            raise HTTPException(404, "not found")
        _refuse_unless_local_dashboard(request)

    def items(request: Request, c: sqlite3.Connection) -> list[DraftItemOut]:
        path = request.app.state.settings.db_path.parent / ALLOWLIST_FILE
        try:
            reg = load()
            allowlist = load_allowlist(path)
        except (RegistryError, DraftAllowlistError, OSError) as exc:
            log.warning("internal drafts show nothing: %s", exc)
            return []
        return [_item(d) for d in draft_summaries(c, reg, allowlist)]

    deps = [Depends(gate)]

    @router.get("/internal/drafts", response_model=DraftFeedOut, dependencies=deps)
    def feed(request: Request, c: Conn, response: Response) -> DraftFeedOut:
        response.headers.update(_HEADERS)
        return DraftFeedOut(items=items(request, c))

    @router.get("/internal/drafts/{summary_id}", response_model=DraftItemOut, dependencies=deps)
    def detail(
        request: Request,
        c: Conn,
        response: Response,
        summary_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    ) -> DraftItemOut:
        found = next((i for i in items(request, c) if i.id == summary_id), None)
        if found is None:
            raise HTTPException(404, "not found")
        response.headers.update(_HEADERS)
        return found

    return router
