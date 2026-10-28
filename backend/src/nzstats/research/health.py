"""Research pipeline health (Phase 3E): one read-only report for an operator or a monitoring job.

Per source: whether any route (crawler or manual import) permits holding its material, the crawler's last state,
the newest stored publication against the registry's optional cadence (`expected_publication_days`), and the work
queues (current versions without a finished summary, verified summaries awaiting review, approved summaries without a
publication decision). It also re-runs the public gate over every summary whose latest decision is `publish`, so a
revoked permission, an institution removed from the registry (listed with routes `unregistered`), a newer document
version or evidence that no longer verifies shows up as a summary that is published but withheld. Globally:
recorded model spend in the rolling window against its cap, and the public API switch.

Nothing is requested or changed, and no reviewer, approver, importer, note or document text is included: the report
can go to a log or a monitoring channel. `needs_attention` is the exit status for a scheduled check.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from nzstats.clock import AKL, to_utc_iso
from nzstats.research import summary_store as ss
from nzstats.research.api import ENABLE_ENV, public_research_enabled
from nzstats.research.contract import PERIOD_DAYS, LlmLimits
from nzstats.research.public import public_summaries, why_not_public
from nzstats.research.quality import version_quality
from nzstats.research.registry import Institution
from nzstats.research.summarise import stale_after

BUDGET_WARNING_SHARE = 0.8  # spend at or above this share of the rolling cap needs attention
REPEATED_FAILURES = 3


@dataclass(frozen=True)
class Finding:
    severity: str  # attention | info
    code: str
    message: str


@dataclass
class SourceHealth:
    key: str
    permitted: bool
    routes: str  # crawler, manual import, both, none
    crawler_state: str | None = None
    last_success_at: str | None = None
    newest_publication_on: str | None = None
    last_manual_import_at: str | None = None
    publications: int = 0
    unsummarised: int = 0
    awaiting_review: int = 0
    awaiting_publication: int = 0
    public: int = 0
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append(Finding(severity, code, message))


@dataclass
class HealthReport:
    checked_at: str
    sources: list[SourceHealth]
    spent_period_usd: float
    period_cap_usd: float
    public_switch: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        every = [*self.findings, *(f for s in self.sources for f in s.findings)]
        return any(f.severity == "attention" for f in every)

    def source(self, key: str) -> SourceHealth:
        return next(s for s in self.sources if s.key == key)

    def to_dict(self) -> dict:
        return {**asdict(self), "needs_attention": self.needs_attention}


def _routes(inst: Institution) -> str:
    crawler, manual = inst.automated_access_allowed, inst.manual_import_allowed
    return (
        "both"
        if crawler and manual
        else "crawler"
        if crawler
        else "manual import"
        if manual
        else "none"
    )


def _one(conn: sqlite3.Connection, inst: Institution, now: datetime) -> SourceHealth:
    src = SourceHealth(inst.key, inst.source_permitted, _routes(inst))
    row = conn.execute(
        "SELECT i.id, h.state, h.last_success_at, h.consecutive_failures FROM research_institution i"
        " LEFT JOIN research_source_health h ON h.institution_id = i.id WHERE i.key = ?",
        (inst.key,),
    ).fetchone()
    if not inst.source_permitted:
        src.add("info", "gated", "no route permits holding this source's material")
        return src
    if row is not None:
        src.crawler_state, src.last_success_at = row["state"], row["last_success_at"]
        stats = conn.execute(
            "SELECT COUNT(*) AS n, MAX(published_on) AS newest FROM research_publication"
            " WHERE institution_id = ? AND duplicate_of_id IS NULL", (row["id"],)).fetchone()  # fmt: skip
        src.publications, src.newest_publication_on = stats["n"], stats["newest"]
        src.last_manual_import_at = conn.execute(
            "SELECT MAX(imported_at) FROM research_manual_import WHERE institution_id = ?",
            (row["id"],),
        ).fetchone()[0]
        if inst.automated_access_allowed and src.crawler_state in ("blocked", "failing"):
            src.add("attention", f"crawler_{src.crawler_state}",
                    f"the last crawler run was {src.crawler_state}; see `research status`")  # fmt: skip
        if (
            inst.automated_access_allowed
            and (row["consecutive_failures"] or 0) >= REPEATED_FAILURES
        ):
            src.add("attention", "repeated_failures",
                    f"{row['consecutive_failures']} consecutive crawler runs without success")  # fmt: skip
        _queues(conn, row["id"], src)
    if not src.publications:
        src.add("attention", "no_publications", "permitted, but no publication is stored yet")
    elif inst.expected_publication_days and src.newest_publication_on:
        today = now.astimezone(AKL).date()
        age = (today - date.fromisoformat(src.newest_publication_on)).days
        if age > inst.expected_publication_days:
            src.add("attention", "stale",
                    f"newest stored publication is {src.newest_publication_on} ({age} days old); one is"
                    f" expected at least every {inst.expected_publication_days} days")  # fmt: skip
    return src


def _queues(conn: sqlite3.Connection, inst_id: int, src: SourceHealth) -> None:
    src.unsummarised = conn.execute(
        "SELECT COUNT(*) FROM research_publication p WHERE p.institution_id = ? AND p.duplicate_of_id IS NULL"
        " AND p.current_version_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM research_summary s"
        " WHERE s.version_id = p.current_version_id AND s.status != 'provider_error')", (inst_id,),
    ).fetchone()[0]  # fmt: skip
    joined = (
        " FROM research_summary s JOIN research_document_version v ON v.id = s.version_id"
        " JOIN research_publication p ON p.id = v.publication_id WHERE p.institution_id = ?"
    )
    src.awaiting_review = conn.execute(
        f"SELECT COUNT(*){joined} AND s.status = 'verified' AND s.review_status = 'unreviewed'",
        (inst_id,),
    ).fetchone()[0]
    src.awaiting_publication = conn.execute(
        f"SELECT COUNT(*){joined} AND s.status = 'verified' AND s.review_status = 'approved' AND NOT EXISTS"
        " (SELECT 1 FROM research_summary_publication d WHERE d.summary_id = s.id)", (inst_id,),
    ).fetchone()[0]  # fmt: skip
    poor = [
        r[0] for r in conn.execute(
            "SELECT current_version_id FROM research_publication WHERE institution_id = ?"
            " AND current_version_id IS NOT NULL ORDER BY id", (inst_id,))
        if (q := version_quality(conn, r[0])) is not None and q.grade == "poor"
    ]  # fmt: skip
    if poor:
        src.add("attention", "poor_extraction",
                f"current versions graded poor: {', '.join(map(str, poor))}; see `research quality`")  # fmt: skip


def _published_ids(conn: sqlite3.Connection) -> dict[str, list[int]]:
    """Institution key -> its summaries whose latest publication decision is `publish`, whether or not the key is
    still in the registry (one query for every institution)."""
    out: dict[str, list[int]] = {}
    for key, sid in conn.execute(
        "SELECT i.key, s.id FROM research_summary s JOIN research_document_version v ON v.id = s.version_id"
        " JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id WHERE"
        " (SELECT d.decision FROM research_summary_publication d WHERE d.summary_id = s.id"
        "  ORDER BY d.id DESC LIMIT 1) = 'publish' ORDER BY i.key, s.id"
    ):
        out.setdefault(key, []).append(int(sid))
    return out


def research_health(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    *,
    now: datetime,
    limits: LlmLimits,
    env: Mapping[str, str],
) -> HealthReport:
    sources = [_one(conn, inst, now) for inst in registry.values()]
    published = _published_ids(conn)
    # an institution removed from the registry is withheld by the public gate, so it is audited too
    sources += [
        SourceHealth(key, permitted=False, routes="unregistered")
        for key in published
        if key not in registry
    ]
    shown = {p.id for p in public_summaries(conn, registry)}
    for src in sources:
        for sid in published.get(src.key, ()):
            if sid in shown:
                src.public += 1
                continue
            reason = why_not_public(conn, registry, sid)
            if reason and not reason.startswith("superseded"):
                hint = (
                    f"; restore its registry entry or run `research withdraw {sid}`"
                    if src.key not in registry
                    else ""
                )
                src.add("attention", "published_but_withheld",
                        f"summary {sid} is published but withheld: {reason}{hint}")  # fmt: skip
    spent = ss.spent_since(conn, now - timedelta(days=PERIOD_DAYS))
    report = HealthReport(now.astimezone(AKL).isoformat(timespec="seconds"), sources, round(spent, 6),
                          limits.max_period_usd, "on" if public_research_enabled(env) else "off")  # fmt: skip
    if spent >= BUDGET_WARNING_SHARE * limits.max_period_usd:
        report.findings.append(Finding(
            "attention", "budget_near_cap",
            f"${spent:.2f} of the ${limits.max_period_usd:.2f} {PERIOD_DAYS}-day model budget is spent"))  # fmt: skip
    _unsettled_calls(conn, report, now, limits)
    if report.public_switch == "on":
        report.findings.append(Finding(
            "info", "public_api_on", f"{ENABLE_ENV}=1: published research is served without authentication"))  # fmt: skip
    return report


def _unsettled_calls(
    conn: sqlite3.Connection, report: HealthReport, now: datetime, limits: LlmLimits
) -> None:
    """Calls whose outcome is unknown (the process died, or the call was interrupted). They count at their worst
    case until they leave the rolling window; a young held one may simply be a call in flight."""
    stamp = to_utc_iso(now - timedelta(days=PERIOD_DAYS))
    in_flight = to_utc_iso(now - stale_after(limits))
    rows = [
        r for r in ss.open_reservations(conn)
        if r["created_at"] >= stamp and (r["state"] == "abandoned" or r["created_at"] < in_flight)
    ]  # fmt: skip
    if rows:
        held = sum(r["reserved_usd"] for r in rows)
        report.findings.append(Finding(
            "attention", "unsettled_model_calls",
            f"{len(rows)} model call(s) have an unknown outcome and count as ${held:.2f} spent until they leave"
            f" the {PERIOD_DAYS}-day window; check the provider's billing before raising the cap"))  # fmt: skip
