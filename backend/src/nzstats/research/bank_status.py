"""Bank source states and metrics (Phase 4AE). Read-only: no request, no write, no document text.

A bank's state is the worst of its report series (staleness is judged per series against the adapter's cadence, so a
fresh weekly note cannot mask a missing quarterly outlook). Precedence, worst first:

    permission_denied > unsupported > blocked > missing > undated > stale > ok

`permission_denied` is the real state of every bank until the owner approves a route; it is expected, not a fault, and
`bank_status_exit` treats it, `unsupported` and `ok` as success. Four dates are kept apart: when the newest document
was published, when it was ingested, when it was last analysed, and when the source was last checked.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from nzstats.clock import AKL, to_akl_iso, to_utc_iso
from nzstats.research.banks import ADAPTERS, BankAdapter, adapter_for
from nzstats.research.registry import Institution

State = Literal["ok", "stale", "undated", "missing", "blocked", "unsupported", "permission_denied"]
PRECEDENCE: tuple[State, ...] = (
    "permission_denied", "unsupported", "blocked", "missing", "undated", "stale", "ok",
)  # fmt: skip
SUCCESS: frozenset[State] = frozenset({"ok", "permission_denied", "unsupported"})

_DOCUMENTS = (
    "SELECT p.canonical_url, p.title, p.published_on,"
    " (SELECT MAX(v.extracted_at) FROM research_document_version v WHERE v.publication_id = p.id) AS ingested_at,"
    " (SELECT MAX(s.created_at) FROM research_summary s JOIN research_document_version v ON v.id = s.version_id"
    "  WHERE v.publication_id = p.id AND s.status IN ('verified', 'failed_verification')) AS analysed_at"
    " FROM research_publication p JOIN research_institution i ON i.id = p.institution_id"
    " WHERE i.key = ? AND p.duplicate_of_id IS NULL"
)


@dataclass(frozen=True)
class SeriesStatus:
    series_key: str
    series_name: str
    state: State
    newest_published_on: str | None
    ingested_at: str | None
    analysed_at: str | None
    last_checked_at: str | None


@dataclass(frozen=True)
class BankStatus:
    key: str
    name: str
    state: State
    series: tuple[SeriesStatus, ...]


@dataclass(frozen=True)
class BankMetrics:
    discovery_ok: int = 0
    discovery_failed: int = 0
    new_documents: int = 0
    updated_versions: int = 0
    blocked: int = 0
    extraction_failures: int = 0
    verification_failures: int = 0
    missing_expected: int = 0


def _worst(states: list[State]) -> State:
    return next((s for s in PRECEDENCE if s in states), "ok")


def _crawler(conn: sqlite3.Connection, key: str) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT h.state, h.last_checked_at FROM research_institution i"
        " JOIN research_source_health h ON h.institution_id = i.id WHERE i.key = ?",
        (key,),
    ).fetchone()
    return (row["state"], row["last_checked_at"]) if row else (None, None)


def _series_statuses(
    conn: sqlite3.Connection, inst: Institution, adapter: BankAdapter, now: datetime
) -> tuple[SeriesStatus, ...]:
    crawler_state, checked = _crawler(conn, inst.key)
    today = now.astimezone(AKL).date()
    documents = conn.execute(_DOCUMENTS, (inst.key,)).fetchall()
    out = []
    for series in adapter.series:
        mine = [d for d in documents if adapter.series_of(d["canonical_url"], d["title"]) == series]
        published = max((d["published_on"] for d in mine if d["published_on"]), default=None)
        if crawler_state == "blocked" and inst.automated_access_allowed:
            state: State = "blocked"
        elif not mine:
            state = "missing"
        elif published is None:
            state = "undated"  # reports are held but none states a date: freshness cannot be judged, so not "ok"
        elif published and (today - date.fromisoformat(published)).days > series.cadence_days:
            state = "stale"
        else:
            state = "ok"
        out.append(
            SeriesStatus(
                series_key=series.key,
                series_name=series.name,
                state=state,
                newest_published_on=published,
                ingested_at=max((d["ingested_at"] for d in mine if d["ingested_at"]), default=None),
                analysed_at=max((d["analysed_at"] for d in mine if d["analysed_at"]), default=None),
                last_checked_at=checked,
            )
        )
    return tuple(out)


def bank_status(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    now: datetime,
    adapters: Mapping[str, BankAdapter] = ADAPTERS,
) -> list[BankStatus]:
    statuses = []
    for inst in sorted((i for i in registry.values() if i.kind == "bank"), key=lambda i: i.key):
        adapter = adapter_for(inst.key, adapters)
        if not inst.source_permitted:
            denied = tuple(
                SeriesStatus(s.key, s.name, "permission_denied", None, None, None, None)
                for s in (adapter.series if adapter else ())
            )
            statuses.append(BankStatus(inst.key, inst.name, "permission_denied", denied))
        elif adapter is None:
            statuses.append(BankStatus(inst.key, inst.name, "unsupported", ()))
        else:
            series = _series_statuses(conn, inst, adapter, now)
            statuses.append(
                BankStatus(inst.key, inst.name, _worst([s.state for s in series]), series)
            )
    return statuses


def _akl(value: str | None) -> str:
    return to_akl_iso(value) if value else "-"


def render_text(statuses: list[BankStatus]) -> list[str]:
    """The `bank-status` report as lines: times in Pacific/Auckland (the JSON form keeps UTC). No document text."""
    lines = [
        "Bank sources. Read-only: nothing was requested or changed. Times are Pacific/Auckland;"
        " `--json` keeps UTC.",
        f"{'bank':<10} {'state':<18} series",
    ]
    for s in statuses:
        lines.append(f"{s.key:<10} {s.state:<18}")
        for x in s.series:
            lines.append(
                f"  {x.series_key:<30} {x.state:<18} published {x.newest_published_on or '-':<11}"
                f" ingested {_akl(x.ingested_at):<26} analysed {_akl(x.analysed_at):<26}"
                f" checked {_akl(x.last_checked_at)}"
            )
    return lines


def bank_status_exit(statuses: list[BankStatus]) -> int:
    """0 when every bank is ok, permission_denied or unsupported; 1 when a permitted bank needs attention."""
    return 0 if all(s.state in SUCCESS for s in statuses) else 1


def bank_metrics(
    conn: sqlite3.Connection,
    registry: Mapping[str, Institution],
    since: datetime,
    *,
    now: datetime,
    adapters: Mapping[str, BankAdapter] = ADAPTERS,
) -> dict[str, BankMetrics]:
    stamp = to_utc_iso(since)
    expected = {
        s.key: sum(x.state in ("missing", "stale") for x in s.series)
        for s in bank_status(conn, registry, now, adapters)
    }
    out = {}
    for inst in sorted((i for i in registry.values() if i.kind == "bank"), key=lambda i: i.key):
        key = inst.key
        out[key] = BankMetrics(
            discovery_ok=_runs(conn, key, stamp, "ok", "partial"),
            discovery_failed=_runs(conn, key, stamp, "failed"),
            new_documents=_items(conn, key, stamp, "new"),
            updated_versions=_items(conn, key, stamp, "updated"),
            blocked=_runs(conn, key, stamp, "blocked"),
            extraction_failures=_items(conn, key, stamp, "failed"),
            verification_failures=_verification_failures(conn, key, stamp),
            missing_expected=expected.get(key, 0),
        )
    return out


def _runs(conn: sqlite3.Connection, key: str, stamp: str, *outcomes: str) -> int:
    marks = ",".join("?" * len(outcomes))
    return conn.execute(
        "SELECT COUNT(*) FROM research_run r JOIN research_institution i ON i.id = r.institution_id"
        f" WHERE i.key = ? AND r.dry_run = 0 AND r.started_at >= ? AND r.outcome IN ({marks})",
        (key, stamp, *outcomes),
    ).fetchone()[0]


def _items(conn: sqlite3.Connection, key: str, stamp: str, outcome: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM research_run_item t JOIN research_run r ON r.id = t.run_id"
        " JOIN research_institution i ON i.id = r.institution_id"
        " WHERE i.key = ? AND r.dry_run = 0 AND r.started_at >= ? AND t.outcome = ?",
        (key, stamp, outcome),
    ).fetchone()[0]


def _verification_failures(conn: sqlite3.Connection, key: str, stamp: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM research_summary s JOIN research_document_version v ON v.id = s.version_id"
        " JOIN research_publication p ON p.id = v.publication_id"
        " JOIN research_institution i ON i.id = p.institution_id"
        " WHERE i.key = ? AND s.status = 'failed_verification' AND s.created_at >= ?",
        (key, stamp),
    ).fetchone()[0]
