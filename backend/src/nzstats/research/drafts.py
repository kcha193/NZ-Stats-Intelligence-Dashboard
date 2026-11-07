"""The one gate for internal drafts: AI summaries shown on this machine with their failed checks. Never public.

A draft may have failed the evidence checks, and no reviewer has to have approved it, so this is deliberately a
separate gate from `public.py` and `private.py`, and admits nothing to either. It is served only on loopback, by
`nzstats serve --internal-drafts` (`drafts_api.py`). A summary is shown only when the owner's list names it by id and
exact output hash, it holds a parsed output, no reviewer has rejected it, its document is current, held and not a
duplicate, its institution allows quoting, and no section reads like instructions to a model. The checks are rerun
on each call and every claim carries its own result, so a draft can never be mistaken for a verified summary.

`stored_reports` lists what is held, by title, date and address only, so a report with no summary yet is not hidden
and the newest one is known from the institution's own publication date, never from the order of import.

The list lives beside the database under `data/` (`internal-drafts.json`, never in Git). A missing file means no
drafts; a malformed one is refused and shows nothing.

Phase 4T adds an opt-in automatic mode (`auto_display` in the same file). It removes the per-summary entry, not a
check: every eligible summary is shown, newest per document version, only when it is also complete, schema-valid
output whose stored metadata shows a reviewed route (`_integrity_refusal`), and the owner has not withdrawn it. The
explicit list keeps its Phase 4P meaning when `auto_display` is absent. A withdrawal applies in both modes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from nzstats.research.contract import OutlookSummary
from nzstats.research.openrouter import ROUTES
from nzstats.research.prompt import injection_findings
from nzstats.research.public import SUMMARY_SELECT, allowed_document_url
from nzstats.research.registry import ContentPolicy, Institution
from nzstats.research.summarise import load_sections
from nzstats.research.summary_store import is_redacted
from nzstats.research.verify import Problem, VerificationContext, verify

log = logging.getLogger(__name__)
ALLOWLIST_FILE = "internal-drafts.json"
SHOWABLE_STATUSES = ("verified", "failed_verification")
UNUSABLE_STATUSES = ("invalid_output", "provider_error")
ClaimStatus = Literal["clean", "warning", "failed"]
# What the automated checks found, never a certainty: "no_automated_issue" is not "verified". An unusable response
# (malformed, truncated, refused, route-unverified) is only ever counted, never shown as commentary.
ValidationCategory = Literal[
    "no_automated_issue", "automated_warning", "failed_automated_checks", "unusable_response"
]
VALIDATION_CATEGORIES: tuple[str, ...] = ValidationCategory.__args__
# Only a local model run on this machine, besides the reviewed OpenRouter routes, may be shown automatically.
LOCAL_PROVIDERS = frozenset({"openai_compatible"})
_PRIVACY = {
    "zdr": True,
    "data_collection": "deny",
    "allow_fallbacks": False,
    "require_parameters": True,
}


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


class AutoDisplay(_Strict):
    """The owner's switch for automatic drafts. Only an explicit `true` turns it on."""

    enabled: Literal[True]
    enabled_by: str = Field(min_length=1)
    enabled_on: date
    note: str = Field(min_length=1)


class Withdrawal(_Strict):
    summary_id: int = Field(ge=1)
    withdrawn_by: str = Field(min_length=1)
    withdrawn_on: date
    note: str = Field(min_length=1)


class DraftAllowlist(_Strict):
    drafts: tuple[DraftEntry, ...] = ()
    auto_display: AutoDisplay | None = None
    withdrawn: tuple[Withdrawal, ...] = ()

    @field_validator("drafts", "withdrawn")
    @classmethod
    def _one_decision_per_summary(cls, items: tuple) -> tuple:
        if len({d.summary_id for d in items}) != len(items):
            raise ValueError("a summary may be listed once")
        return items

    @property
    def auto(self) -> bool:
        return self.auto_display is not None

    def withdrew(self, summary_id: int) -> bool:
        return any(w.summary_id == summary_id for w in self.withdrawn)


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

    @property
    def category(self) -> ValidationCategory:
        if not self.passed:
            return "failed_automated_checks"
        return "automated_warning" if self.warnings else "no_automated_issue"


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


def _integrity_refusal(conn: sqlite3.Connection, row: Mapping[str, Any]) -> str | None:
    """Why stored metadata does not show a complete response from a reviewed route, or None.

    The pipeline checked the response when it arrived; this rechecks what it recorded, so a summary written by an
    unreviewed provider, a fallback route or a changed output is never shown without someone naming it.
    """
    stored = conn.execute(
        "SELECT output_sha256, raw_output, parameters FROM research_summary WHERE id = ?",
        (row["id"],),
    ).fetchone()
    raw = stored["raw_output"]
    if raw is None or is_redacted(raw) or stored["output_sha256"] is None:
        return "the stored output is not complete"
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != stored["output_sha256"]:
        return "the stored output does not match its recorded hash"
    try:
        params = json.loads(stored["parameters"] or "{}")
    except ValueError:
        return "the stored request parameters are not readable"
    if not isinstance(params, dict):
        return "the stored request parameters are not readable"
    # A truncated or refused response is stored as a provider error today; this does not rely on that mapping.
    if params.get("finish_reason") != "stop":
        return "the response did not record a normal finish"
    if row["provider"] in LOCAL_PROVIDERS and not row["hosted"]:
        return None
    if row["provider"] != "openrouter" or not row["hosted"]:
        return "the provider is not a reviewed route for automatic drafts"
    route = next((r for r in ROUTES if r.model == row["model"]), None)
    if (
        route is None
        or params.get("provider_only") != route.provider_id
        or any(params.get(k) != v for k, v in _PRIVACY.items())
    ):
        return "the stored request does not show the reviewed route and privacy settings"
    if params.get("serving_provider") != route.response_provider or not re.fullmatch(
        r"gen-[A-Za-z0-9_-]{1,180}", str(params.get("response_id", ""))
    ):
        return "the response's serving provider or identity was not recorded"
    calls = conn.execute(
        "SELECT outcome, model FROM research_llm_usage WHERE summary_id = ?", (row["id"],)
    ).fetchall()
    if not calls or any(c["outcome"] != "ok" or c["model"] != row["model"] for c in calls):
        return "no completed, billed call is recorded for this output"
    return None


def _assess(
    conn: sqlite3.Connection,
    row: Mapping[str, Any],
    entry: DraftEntry | None,
    registry: Mapping[str, Institution],
    allowlist: DraftAllowlist,
) -> tuple[str | None, DraftSummary | None]:
    """`entry` is the owner's named decision (list mode) or None (auto mode, which checks integrity instead)."""
    if row["status"] not in SHOWABLE_STATUSES:
        return f"no usable output ({row['status']})", None
    if entry is not None:
        stored = conn.execute(
            "SELECT output_sha256 FROM research_summary WHERE id = ?", (row["id"],)
        ).fetchone()[0]
        if stored != entry.output_sha256:
            return "the stored output is not the one the owner named", None
    if row["review_status"] == "rejected":
        return "a reviewer rejected it", None
    if allowlist.withdrew(int(row["id"])):
        return "the owner withdrew it", None
    if entry is None and (refusal := _integrity_refusal(conn, row)):
        return refusal, None
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
    if not inst.holds(row["acquisition"]):
        return "the approval that let this document in was revoked", None
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
    published = _civil_date(row["published_on"])
    if row["published_on"] and published is None:
        return "the stored publication date is not valid", None
    report = verify(summary, sections, VerificationContext(
        published_on=published, institution=row["institution"]))  # fmt: skip
    # The document's own stated date or period, set only from its text (never derived from the publication date).
    stated = conn.execute(
        "SELECT reference_period FROM research_publication WHERE id = ?", (row["publication_id"],)
    ).fetchone()
    draft = DraftSummary(
        int(row["id"]), inst, summary, report.passed, len(report.warnings),
        _claims(summary, report.errors, report.warnings),
        {**dict(row), "reference_period": stated[0] if stated else None},
    )  # fmt: skip
    return None, draft


def _auto_assessed(
    conn: sqlite3.Connection, registry: Mapping[str, Institution], allowlist: DraftAllowlist
) -> list[tuple[Mapping[str, Any], str | None, DraftSummary | None]]:
    """Every summary with output. The newest one of each document version holds its slot even when it is refused
    (withdrawn, rejected, failed integrity), so an older output never resurfaces in its place."""
    marks = ",".join("?" * len(SHOWABLE_STATUSES))
    rows = conn.execute(
        f"{SUMMARY_SELECT} WHERE s.status IN ({marks}) ORDER BY p.published_on DESC, s.id DESC",
        SHOWABLE_STATUSES,
    ).fetchall()
    shown: dict[int, int] = {}
    out = []
    for row in sorted(rows, key=lambda r: -int(r["id"])):
        if row["version_id"] in shown:
            newer = shown[row["version_id"]]
            out.append((row, f"superseded by summary {newer} of the same document version", None))
            continue
        reason, draft = _assess(conn, row, None, registry, allowlist)
        shown[row["version_id"]] = int(row["id"])
        out.append((row, reason, draft))
    order = {int(r["id"]): i for i, r in enumerate(rows)}
    return sorted(out, key=lambda item: order[int(item[0]["id"])])


def draft_summaries(
    conn: sqlite3.Connection, registry: Mapping[str, Institution], allowlist: DraftAllowlist
) -> list[DraftSummary]:
    """Every draft that may be shown now, newest publication first."""
    if allowlist.auto:
        assessed = _auto_assessed(conn, registry, allowlist)
    else:
        entries = {e.summary_id: e for e in allowlist.drafts}
        if not entries:
            return []
        marks = ",".join("?" * len(entries))
        rows = conn.execute(
            f"{SUMMARY_SELECT} WHERE s.id IN ({marks}) ORDER BY p.published_on DESC, s.id DESC",
            tuple(entries),
        ).fetchall()
        assessed = [
            (row, *_assess(conn, row, entries[row["id"]], registry, allowlist)) for row in rows
        ]
    out = []
    for row, reason, draft in assessed:
        if draft is not None:
            out.append(draft)
        elif not (reason or "").startswith("superseded"):
            log.info("internal draft %s withheld: %s", row["id"], reason)
    return out


@dataclass(frozen=True)
class StoredReport:
    publication_id: int
    institution: Institution
    title: str
    url: str
    series: str | None
    published_on: date | None
    newest: bool  # published on the institution's latest date among the reports listed; a tie marks each
    unusable_attempts: int = (
        0  # responses on the current version that are never shown (malformed, refused, ...)
    )


def _civil_date(text: str | None) -> date | None:
    """A stored publication date, or None when it is absent or malformed: never a guess."""
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        log.warning("a stored publication date is not a valid date")
        return None


def stored_reports(
    conn: sqlite3.Connection, registry: Mapping[str, Institution]
) -> list[StoredReport]:
    """Current, held, non-duplicate reports, latest publication date first; undated ones last and never newest."""
    unusable = ",".join("?" * len(UNUSABLE_STATUSES))
    rows = conn.execute(
        "SELECT p.id, i.key, p.title, p.canonical_url, p.series, p.published_on, v.acquisition,"
        f" (SELECT COUNT(*) FROM research_summary s WHERE s.version_id = v.id AND s.status IN ({unusable}))"
        " AS unusable FROM research_publication p JOIN research_institution i ON i.id = p.institution_id"
        " JOIN research_document_version v ON v.id = p.current_version_id"
        " WHERE p.duplicate_of_id IS NULL AND v.purged_at IS NULL AND v.superseded_at IS NULL",
        UNUSABLE_STATUSES,
    ).fetchall()
    held = []
    for row in rows:
        inst = registry.get(row["key"])
        if (
            inst is None
            or inst.content_policy is not ContentPolicy.FULL_TEXT
            or not inst.holds(row["acquisition"])
            or not allowed_document_url(row["canonical_url"], inst)
        ):
            continue
        held.append((row, inst, _civil_date(row["published_on"])))
    latest: dict[str, date] = {}
    for _, inst, published in held:
        if published is not None:
            latest[inst.key] = max(published, latest.get(inst.key, published))
    held.sort(key=lambda h: (h[2] is None, -(h[2].toordinal() if h[2] else 0), -int(h[0]["id"])))
    out = [
        StoredReport(int(row["id"]), inst, row["title"], row["canonical_url"], row["series"], published,
                     published is not None and published == latest[inst.key], int(row["unusable"]))
        for row, inst, published in held
    ]  # fmt: skip
    return out


def why_not_draft(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    allowlist: DraftAllowlist,
    summary_id: int,
) -> str | None:
    """Why this summary is not shown as a draft, in plain words (operator only); None when it is."""
    if allowlist.auto:
        row = conn.execute(f"{SUMMARY_SELECT} WHERE s.id = ?", (summary_id,)).fetchone()
        if row is None:
            return f"no summary {summary_id}"
        if row["status"] not in SHOWABLE_STATUSES:
            return f"no usable output ({row['status']})"
        found = next(
            (a for a in _auto_assessed(conn, registry, allowlist) if a[0]["id"] == summary_id), None
        )
        return found[1] if found is not None else "not found"
    entry = next((e for e in allowlist.drafts if e.summary_id == summary_id), None)
    if entry is None:
        return "not on the internal draft list"
    row = conn.execute(f"{SUMMARY_SELECT} WHERE s.id = ?", (summary_id,)).fetchone()
    if row is None:
        return f"no summary {summary_id}"
    return _assess(conn, row, entry, registry, allowlist)[0]
