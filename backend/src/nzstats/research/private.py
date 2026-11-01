"""The one gate between stored research summaries and the owner's private preview (Phase 4I). Never public.

Separate from `public.py` in both directions: a publication decision neither admits nor withholds anything here,
and nothing admitted here becomes public. The preview is served only on loopback, by `nzstats serve
--private-research` (`private_api.py`). A summary is shown only when every rule holds, checked on each call against
the current database and registry: verified, approved by a reviewer (an unreviewed or rejected summary is never
shown, labelled or not), the newest approved summary of the current version of a non-duplicate publication that has
not been purged, from an institution whose current registry entry allows private display (which also needs the
material still held and its LLM permission still covering the model that wrote the summary), with an https document
address on that institution's allowed hosts, and still passing the current verifier on the stored text with no
section that reads like instructions to a model. `why_not_private` gives the operator the reason.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from nzstats.research.contract import OutlookSummary
from nzstats.research.public import SUMMARY_SELECT, allowed_document_url, current_evidence
from nzstats.research.registry import Institution, PrivateDisplay

log = logging.getLogger(__name__)

_APPROVED = " WHERE s.status = 'verified' AND s.review_status = 'approved'"


@dataclass(frozen=True)
class PrivateSummary:
    id: int
    institution: Institution
    summary: OutlookSummary
    warnings: int
    row: Mapping[str, Any]


def _newest_approved(conn: sqlite3.Connection) -> dict[int, int]:
    """Document version id -> its newest reviewer-approved summary (older approved ones are superseded)."""
    return {
        int(r[0]): int(r[1])
        for r in conn.execute(
            f"SELECT s.version_id, MAX(s.id) FROM research_summary s{_APPROVED} GROUP BY s.version_id"
        )
    }


def _assess(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    registry: Mapping[str, Institution],
    newest: Mapping[int, int],
) -> tuple[str | None, PrivateSummary | None]:
    if row["status"] != "verified":
        return f"not verified ({row['status']})", None
    if row["review_status"] != "approved":
        return f"not approved by a reviewer ({row['review_status']})", None
    if newest.get(row["version_id"]) != row["id"]:
        return (
            f"superseded by summary {newest.get(row['version_id'])} of the same document version",
            None,
        )
    if row["purged_at"]:
        return "the source text was purged", None
    if row["current_version_id"] != row["version_id"] or row["superseded_at"]:
        return "the document has a newer version; summarise it again", None
    if row["duplicate_of_id"] is not None:
        return "the publication is a duplicate of another stored document", None
    inst = registry.get(row["institution"])
    if inst is None:
        return "the institution is not in the research registry", None
    if inst.private_display_level(row["acquisition"]) is PrivateDisplay.NONE:
        return (
            "the registry shows nothing privately for this source (private_display, access or LLM permission)",
            None,
        )
    if inst.llm_refusal(hosted=bool(row["hosted"]), acquisition=row["acquisition"]):
        return "the model that wrote it is no longer permitted for this source", None
    if not allowed_document_url(row["canonical_url"], inst):
        return "the document address is not https on one of the institution's allowed hosts", None
    reason, summary, warnings = current_evidence(conn, row)
    if summary is None:
        return reason, None
    return None, PrivateSummary(int(row["id"]), inst, summary, warnings, dict(row))


def private_summaries(
    conn: sqlite3.Connection, registry: Mapping[str, Institution]
) -> list[PrivateSummary]:
    """Every summary the private preview may show now, newest publication first."""
    newest = _newest_approved(conn)
    rows = conn.execute(
        f"{SUMMARY_SELECT}{_APPROVED} ORDER BY p.published_on DESC, s.id DESC"
    ).fetchall()
    out = []
    for row in rows:
        reason, item = _assess(conn, row, registry, newest)
        if item is not None:
            out.append(item)
        elif reason and not reason.startswith("superseded"):
            log.info("research summary %s withheld from the private preview: %s", row["id"], reason)
    return out


def why_not_private(
    conn: sqlite3.Connection, registry: Mapping[str, Institution], summary_id: int
) -> str | None:
    """Why this summary is not in the private preview, in plain words (operator only); None when it is."""
    row = conn.execute(f"{SUMMARY_SELECT} WHERE s.id = ?", (summary_id,)).fetchone()
    if row is None:
        return f"no summary {summary_id}"
    return _assess(conn, row, registry, _newest_approved(conn))[0]
