"""The one gate between stored research summaries and anything public (Phase 3C).

A summary is public only when every rule holds, checked on each call against the current database and registry:
verified, approved by a reviewer, publication-approved (latest decision `publish`), the newest such summary of the
current version of a non-duplicate publication, from an institution whose current registry entry allows display,
with an https document address on that institution's allowed hosts, and still passing the current verifier on the
stored text with no section that reads like instructions to a model. Anything else is left out without a public
explanation; `why_not_public` gives the operator the reason.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import ValidationError

from nzstats.research.contract import OutlookSummary
from nzstats.research.prompt import injection_findings
from nzstats.research.registry import Institution, PublicDisplay
from nzstats.research.safety import HostPolicy, UnsafeUrl
from nzstats.research.summarise import load_sections
from nzstats.research.verify import VerificationContext, resolve_verifier, verify

log = logging.getLogger(__name__)

_LATEST_DECISION = "SELECT {col} FROM research_summary_publication d WHERE d.summary_id = s.id ORDER BY d.id DESC LIMIT 1"
SUMMARY_SELECT = (
    "SELECT s.id, s.version_id, s.status, s.review_status, s.reviewed_at, s.output_json, s.provider, s.model,"
    " s.hosted, s.prompt_version, s.processing_version, s.verifier_version, s.created_at,"
    f" ({_LATEST_DECISION.format(col='decision')}) AS decision,"
    f" ({_LATEST_DECISION.format(col='decided_at')}) AS decided_at,"
    " v.version_no, v.title, v.fetched_at, v.format, v.page_count, v.superseded_at, v.acquisition, v.purged_at,"
    " p.id AS publication_id, p.canonical_url, p.published_on, p.categories, p.current_version_id,"
    " p.duplicate_of_id, i.key AS institution"
    " FROM research_summary s JOIN research_document_version v ON v.id = s.version_id"
    " JOIN research_publication p ON p.id = v.publication_id"
    " JOIN research_institution i ON i.id = p.institution_id"
)
_PUBLISHED = (
    " WHERE s.status = 'verified' AND s.review_status = 'approved'"
    f" AND ({_LATEST_DECISION.format(col='decision')}) = 'publish'"
)


@dataclass(frozen=True)
class PublicSummary:
    id: int
    institution: Institution
    display: PublicDisplay
    summary: OutlookSummary
    warnings: int
    row: Mapping[str, Any]


def _newest_published(conn: sqlite3.Connection) -> dict[int, int]:
    """Document version id -> the newest publication-approved summary of it (older ones are superseded)."""
    return {
        int(r[0]): int(r[1])
        for r in conn.execute(
            f"SELECT s.version_id, MAX(s.id) FROM research_summary s{_PUBLISHED} GROUP BY s.version_id"
        )
    }


def allowed_document_url(url: str | None, inst: Institution) -> bool:
    """The crawler's own URL policy (https, allowed host, canonical path, allow and block lists); no DNS lookup."""
    policy = HostPolicy(inst.allowed_hosts, allowed_path_prefixes=inst.allowed_path_prefixes,
                        blocked_path_prefixes=inst.blocked_path_prefixes, resolver=None)  # fmt: skip
    try:
        policy.check(url or "")
    except (UnsafeUrl, ValueError):
        return False
    return True


def _state_refusal(row: sqlite3.Row, newest: Mapping[int, int]) -> str | None:
    if row["status"] != "verified":
        return f"not verified ({row['status']})"
    if row["review_status"] != "approved":
        return f"not approved by a reviewer ({row['review_status']})"
    if row["decision"] is None:
        return "not publication-approved (no publication decision)"
    if row["decision"] != "publish":
        return "not publication-approved (withdrawn)"
    if newest.get(row["version_id"]) != row["id"]:
        return f"superseded by summary {newest.get(row['version_id'])} of the same document version"
    if row["purged_at"]:
        return "the source text was purged"
    if row["current_version_id"] != row["version_id"] or row["superseded_at"]:
        return "the document has a newer version; summarise it again"
    if row["duplicate_of_id"] is not None:
        return "the publication is a duplicate of another stored document"
    return None


def _assess(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    registry: Mapping[str, Institution],
    newest: Mapping[int, int],
) -> tuple[str | None, PublicSummary | None]:
    reason = _state_refusal(row, newest)
    if reason is not None:
        return reason, None
    inst = registry.get(row["institution"])
    if inst is None:
        return "the institution is not in the research registry", None
    level = inst.display_level(row["acquisition"])
    if level.rank > PublicDisplay.LINK_ONLY.rank and inst.llm_refusal(
        hosted=bool(row["hosted"]), acquisition=row["acquisition"]
    ):
        level = (
            PublicDisplay.LINK_ONLY
        )  # the model that wrote the text is no longer permitted for this source
    if level is PublicDisplay.NONE:
        return (
            "the registry displays nothing for this source (public_display or access not approved)",
            None,
        )
    if not allowed_document_url(row["canonical_url"], inst):
        return "the document address is not https on one of the institution's allowed hosts", None
    reason, summary, warnings = current_evidence(conn, row)
    if summary is None:
        return reason, None
    return None, PublicSummary(int(row["id"]), inst, level, summary, warnings, dict(row))


def current_evidence(
    conn: sqlite3.Connection, row: Mapping[str, Any]
) -> tuple[str | None, OutlookSummary | None, int]:
    """The stored summary re-verified now, on the stored text: (why it fails, or None; the summary; warnings)."""
    try:
        summary = OutlookSummary.model_validate_json(row["output_json"] or "")
    except ValidationError:
        return "the stored output no longer parses as a summary", None, 0
    if summary.version_id != row["version_id"]:
        return "the stored output belongs to a different document version", None, 0
    sections = load_sections(conn, row["version_id"])
    published = date.fromisoformat(row["published_on"]) if row["published_on"] else None
    injected = tuple(injection_findings(sections))
    report = verify(summary, sections, VerificationContext(
        published_on=published, injection_ordinals=injected, institution=row["institution"]),
        version=resolve_verifier(row["verifier_version"]))  # fmt: skip
    if not report.passed:
        return f"the current evidence checks now fail ({len(report.errors)} errors)", None, 0
    if injected:
        return "a section of the document reads like instructions to a model", None, 0
    return None, summary, len(report.warnings)


def public_summaries(
    conn: sqlite3.Connection, registry: Mapping[str, Institution]
) -> list[PublicSummary]:
    """Every summary that may be shown publicly now, newest publication first."""
    newest = _newest_published(conn)
    rows = conn.execute(
        f"{SUMMARY_SELECT}{_PUBLISHED} ORDER BY p.published_on DESC, s.id DESC"
    ).fetchall()
    out = []
    for row in rows:
        reason, item = _assess(conn, row, registry, newest)
        if item is not None:
            out.append(item)
        elif reason and not reason.startswith("superseded"):
            log.info("research summary %s withheld from public view: %s", row["id"], reason)
    return out


def why_not_public(
    conn: sqlite3.Connection, registry: Mapping[str, Institution], summary_id: int
) -> str | None:
    """Why this summary is not public, in plain words (operator only); None when it is."""
    row = conn.execute(f"{SUMMARY_SELECT} WHERE s.id = ?", (summary_id,)).fetchone()
    if row is None:
        return f"no summary {summary_id}"
    return _assess(conn, row, registry, _newest_published(conn))[0]


def topics(row: Mapping[str, Any]) -> list[str]:
    try:
        value = json.loads(row["categories"] or "[]")
    except ValueError:
        return []
    return sorted({str(v) for v in value if isinstance(v, str)}) if isinstance(value, list) else []
