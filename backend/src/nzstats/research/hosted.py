"""Independent version-scoped hosted consent. No CLI loader or implicit approvals.

PR B must supply reviewed records explicitly. Source-wide/local consent never creates one.
An approver must inspect licensing (including third-party material), provider terms and the
exact frozen input scope before signing. This module checks the record, not legal validity.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from nzstats.research.contract import Provider, SectionText, SummaryRequest
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
    approved_section_ordinals: tuple[int, ...]
    sections_sha256: str


def section_inventory_sha256(sections: Mapping[int, SectionText]) -> str:
    """Bind all stored sections, including excluded ones, without exposing their text."""
    rows = [[n, s.text, s.page_start, s.page_end, s.heading] for n, s in sorted(sections.items())]
    return hashlib.sha256(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def approved_sections(
    sections: Mapping[int, SectionText], grant: HostedConsent
) -> dict[int, SectionText]:
    ordinals = grant.approved_section_ordinals
    if (
        not isinstance(ordinals, tuple)
        or not ordinals
        or any(type(n) is not int or n not in sections for n in ordinals)
        or tuple(sorted(set(ordinals))) != ordinals
        or grant.sections_sha256 != section_inventory_sha256(sections)
    ):
        raise ValueError("hosted section scope missing or mismatched")
    return {n: sections[n] for n in ordinals}


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
    sections = {
        r["ordinal"]: SectionText(r["text"], r["page_start"], r["page_end"], r["heading"])
        for r in conn.execute(
            "SELECT ordinal,text,page_start,page_end,heading FROM research_section WHERE version_id=?",
            (request.version_id,),
        )
    }
    try:
        selected = approved_sections(sections, grant)
    except ValueError:
        return refusal
    if tuple(s.ordinal for s in request.sections) != tuple(selected):
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
