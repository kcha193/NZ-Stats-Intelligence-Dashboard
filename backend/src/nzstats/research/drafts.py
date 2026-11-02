"""The one gate for internal drafts: summaries the owner named, shown with their failed checks. Never public.

A draft may have failed the evidence checks, and no reviewer has to have approved it, so this is deliberately a
separate gate from `public.py` and `private.py`, and admits nothing to either. It is served only on loopback, by
`nzstats serve --internal-drafts` (`drafts_api.py`). A summary is shown only when the owner's list names it by id and
exact output hash, it holds a parsed output, no reviewer has rejected it, its document is current, held and not a
duplicate, its institution allows quoting, and no section reads like instructions to a model. The checks are rerun
on each call and every claim carries its own result, so a draft can never be mistaken for a verified summary.

The list lives beside the database under `data/` (`internal-drafts.json`, never in Git). A missing file means no
drafts; a malformed one is refused and shows nothing.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nzstats.research.contract import OutlookSummary
from nzstats.research.prompt import injection_findings
from nzstats.research.public import SUMMARY_SELECT, allowed_document_url
from nzstats.research.registry import ContentPolicy, Institution
from nzstats.research.summarise import load_sections
from nzstats.research.verify import Problem, VerificationContext, verify

log = logging.getLogger(__name__)
ALLOWLIST_FILE = "internal-drafts.json"
SHOWABLE_STATUSES = ("verified", "failed_verification")
ClaimStatus = Literal["clean", "warning", "failed"]


class DraftAllowlistError(ValueError):
    """Fixed, content-free refusal: the file's content is never repeated."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DraftEntry(_Strict):
    summary_id: int = Field(ge=1)
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str = Field(min_length=1)
    approved_on: date
    note: str = Field(min_length=1)


class DraftAllowlist(_Strict):
    drafts: tuple[DraftEntry, ...]

    @field_validator("drafts")
    @classmethod
    def _one_decision_per_summary(cls, drafts: tuple[DraftEntry, ...]) -> tuple[DraftEntry, ...]:
        if len({d.summary_id for d in drafts}) != len(drafts):
            raise ValueError("a summary may be listed once")
        return drafts


def load_allowlist(path: Path) -> DraftAllowlist:
    try:
        return DraftAllowlist.model_validate_json(Path(path).read_bytes())
    except FileNotFoundError:
        return DraftAllowlist(drafts=())
    except (OSError, ValueError, ValidationError) as exc:
        raise DraftAllowlistError("the internal draft list is not valid") from exc


@dataclass(frozen=True)
class DraftClaim:
    path: str
    status: ClaimStatus
    problems: tuple[Problem, ...]


@dataclass(frozen=True)
class DraftSummary:
    id: int
    institution: Institution
    summary: OutlookSummary
    passed: bool
    warnings: int
    claims: tuple[DraftClaim, ...]
    row: Mapping[str, Any]

    @property
    def counts(self) -> dict[str, int]:
        statuses = [c.status for c in self.claims]
        return {status: statuses.count(status) for status in ("clean", "warning", "failed")}


def claim_paths(summary: OutlookSummary) -> list[str]:
    """Every claim's verifier path, in the order the private preview's blocks are built."""
    paths = ["outlook"]
    paths += [f"drivers[{i}]" for i in range(len(summary.drivers))]
    paths += [f"risks[{i}]" for i in range(len(summary.risks))]
    paths += ["uncertainty"] if summary.uncertainty is not None else []
    for name in ("facts", "forecasts", "decisions", "guidance", "assumptions"):
        paths += [f"{name}[{i}]" for i in range(len(getattr(summary, name)))]
    return paths


def _claims(
    summary: OutlookSummary, errors: tuple[Problem, ...], warnings: tuple[Problem, ...]
) -> tuple[DraftClaim, ...]:
    def about(path: str, problems: tuple[Problem, ...]) -> tuple[Problem, ...]:
        return tuple(p for p in problems if p.path == path or p.path.startswith(f"{path}."))

    claims = []
    for path in claim_paths(summary):
        failed, warned = about(path, errors), about(path, warnings)
        status: ClaimStatus = "failed" if failed else "warning" if warned else "clean"
        claims.append(DraftClaim(path, status, failed + warned))
    return tuple(claims)


def _assess(
    conn: sqlite3.Connection,
    row: Mapping[str, Any],
    entry: DraftEntry,
    registry: Mapping[str, Institution],
) -> tuple[str | None, DraftSummary | None]:
    if row["status"] not in SHOWABLE_STATUSES:
        return f"no usable output ({row['status']})", None
    stored = conn.execute(
        "SELECT output_sha256 FROM research_summary WHERE id = ?", (row["id"],)
    ).fetchone()[0]
    if stored != entry.output_sha256:
        return "the stored output is not the one the owner named", None
    if row["review_status"] == "rejected":
        return "a reviewer rejected it", None
    if row["purged_at"]:
        return "the source text was purged", None
    if row["current_version_id"] != row["version_id"] or row["superseded_at"]:
        return "the document has a newer version", None
    if row["duplicate_of_id"] is not None:
        return "the publication is a duplicate of another stored document", None
    inst = registry.get(row["institution"])
    if inst is None:
        return "the institution is not in the research registry", None
    if inst.content_policy is not ContentPolicy.FULL_TEXT:
        return "the source's content policy does not allow quoting", None
    if not allowed_document_url(row["canonical_url"], inst):
        return "the document address is not https on one of the institution's allowed hosts", None
    try:
        summary = OutlookSummary.model_validate_json(row["output_json"] or "")
    except ValidationError:
        return "the stored output no longer parses as a summary", None
    if summary.version_id != row["version_id"]:
        return "the stored output belongs to a different document version", None
    sections = load_sections(conn, row["version_id"])
    if injection_findings(sections):
        return "a section reads like instructions to a model", None
    published = date.fromisoformat(row["published_on"]) if row["published_on"] else None
    report = verify(summary, sections, VerificationContext(
        published_on=published, institution=row["institution"]))  # fmt: skip
    draft = DraftSummary(
        int(row["id"]), inst, summary, report.passed, len(report.warnings),
        _claims(summary, report.errors, report.warnings), dict(row),
    )  # fmt: skip
    return None, draft


def draft_summaries(
    conn: sqlite3.Connection, registry: Mapping[str, Institution], allowlist: DraftAllowlist
) -> list[DraftSummary]:
    """Every draft that may be shown now, newest publication first."""
    entries = {e.summary_id: e for e in allowlist.drafts}
    if not entries:
        return []
    marks = ",".join("?" * len(entries))
    rows = conn.execute(
        f"{SUMMARY_SELECT} WHERE s.id IN ({marks}) ORDER BY p.published_on DESC, s.id DESC",
        tuple(entries),
    ).fetchall()
    out = []
    for row in rows:
        reason, draft = _assess(conn, row, entries[row["id"]], registry)
        if draft is not None:
            out.append(draft)
        else:
            log.info("internal draft %s withheld: %s", row["id"], reason)
    return out


def why_not_draft(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    allowlist: DraftAllowlist,
    summary_id: int,
) -> str | None:
    """Why this summary is not shown as a draft, in plain words (operator only); None when it is."""
    entry = next((e for e in allowlist.drafts if e.summary_id == summary_id), None)
    if entry is None:
        return "not on the internal draft list"
    row = conn.execute(f"{SUMMARY_SELECT} WHERE s.id = ?", (summary_id,)).fetchone()
    if row is None:
        return f"no summary {summary_id}"
    return _assess(conn, row, entry, registry)[0]
