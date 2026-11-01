"""Independent version-scoped hosted consent. No CLI loader or implicit approvals.

PR B must supply reviewed records explicitly. Source-wide/local consent never creates one.
An approver must inspect licensing (including third-party material), provider terms and the
exact frozen input scope before signing. This module checks the record, not legal validity.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from nzstats.research.contract import Provider, SummaryRequest
from nzstats.research.prompt import input_sha256


@dataclass(frozen=True)
class HostedConsent:
    version_id: int
    institution: str
    content_sha256: str
    text_sha256: str
    request_sha256: str
    model: str
    provider_id: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    rights_review: str
    provider_review: str
    budget_approved_usd: float


def consent_refusal(
    conn: sqlite3.Connection,
    request: SummaryRequest,
    provider: Provider,
    consents: Sequence[HostedConsent],
    now: datetime,
) -> str | None:
    """Bind one independently approved version to precisely the text and route being sent."""
    refusal = f"version {request.version_id}: independent hosted consent missing or mismatched"
    if not 1 <= len(consents) <= 2 or any(not isinstance(c, HostedConsent) for c in consents):
        return refusal
    if len({c.version_id for c in consents}) != len(consents):
        return refusal
    grant = next((c for c in consents if c.version_id == request.version_id), None)
    if grant is None:
        return refusal
    row = conn.execute(
        "SELECT content_sha256, text_sha256, purged_at FROM research_document_version WHERE id=?",
        (request.version_id,),
    ).fetchone()
    if row is None or row["purged_at"]:
        return refusal
    if not all(
        isinstance(s, str) and s.strip()
        for s in (grant.approved_by, grant.rights_review, grant.provider_review)
    ):
        return refusal
    if (
        not isinstance(grant.approved_at, datetime)
        or grant.approved_at.tzinfo is None
        or not isinstance(grant.expires_at, datetime)
        or grant.expires_at.tzinfo is None
        or not grant.approved_at <= now < grant.expires_at
        or isinstance(grant.budget_approved_usd, bool)
        or grant.budget_approved_usd != 5
    ):
        return refusal
    expected = input_sha256(
        request, provider=provider.name, model=provider.model, parameters=provider.parameters()
    )
    if (
        grant.institution != request.institution
        or grant.model != provider.model
        or grant.provider_id != provider.parameters().get("provider_only")
        or grant.content_sha256 != row["content_sha256"]
        or grant.text_sha256 != row["text_sha256"]
        or grant.request_sha256 != expected
    ):
        return refusal
    return None
