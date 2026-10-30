"""Plain-text rendering of an `OpsStatus` for the terminal and the local alert report."""

from __future__ import annotations

from datetime import datetime

from nzstats.ops.report import OpsStatus
from nzstats.ops.text import duration

LABEL = {"ok": "OK", "attention": "ATTENTION", "critical": "CRITICAL"}


def _at(value: str | None) -> str:
    if not value:
        return "never"
    from nzstats.ops.text import akl

    return akl(datetime.fromisoformat(value))


def render_text(s: OpsStatus) -> str:
    p, c = s.process, s.calendar
    lines = [
        f"NZ Stats operational status: {LABEL[s.overall]}  ({_at(s.generated_at)})",
        s.summary,
        "",
    ]
    lines.append(f"Collection     {s.collection.mode}: {s.collection.summary}")
    beat = (
        f", heartbeat {duration(p.heartbeat_age_seconds)} ago"
        if p.heartbeat_age_seconds is not None
        else ""
    )
    lines.append(
        f"Process        {p.state}"
        + (f" (pid {p.pid}, started {_at(p.started_at)}{beat})" if p.pid else "")
    )
    r = s.refresh
    if r.state != "never":
        detail = (
            f" ({r.phase}, {duration(r.running_for_seconds or 0)} so far)"
            if r.state == "running"
            else f" at {_at(r.finished_at)}: {r.ingested} ingested, {r.pending} pending, {r.failures} failure(s)"
        )
        lines.append(f"Last check     {r.state}{detail}; last successful {_at(r.last_success_at)}")
    nxt = f"; next {_at(c.next_refresh_at)}" if c.next_refresh_at else ""
    lines.append(f"Calendar       {c.state}; last complete refresh {_at(c.last_success_at)}{nxt}")
    if s.next_release:
        r = s.next_release
        lines.append(
            f"Next release   {r.title} ({r.reference_period or 'n/a'}) at {_at(r.scheduled_at)}; {s.known_upcoming_releases} upcoming"
        )
    else:
        lines.append("Next release   none known for the supported series")
    if s.latest_ingestion:
        lines.append(
            f"Last ingestion {s.latest_ingestion.release_key} {s.latest_ingestion.outcome} at {_at(s.latest_ingestion.finished_at)}"
        )
    else:
        lines.append("Last ingestion none recorded")
    b = s.backup
    if b.latest_good:
        lines.append(
            f"Backup         {b.state}: {b.latest_good.name} ({b.latest_good.kind}, {b.latest_good.verification}, {duration(b.latest_good.age_hours * 3600)} old)"
        )
    else:
        lines.append(f"Backup         {b.state}: nothing usable in {b.directory}")
    d = s.alert_delivery
    lines.append(
        f"Alert delivery {d.state}"
        + (f" ({d.failures} failure(s) in {d.window_hours} h)" if d.failures else "")
    )
    if s.freshness:
        lines += ["", "Freshness (newest ingested release per series)"]
        for f in s.freshness:
            ref = f.latest_reference_period or "-"
            nxt = f"; next {_at(f.next_release_at)}" if f.next_release_at else ""
            lines.append(
                f"  {f.label[:34]:<34} ref {ref:<8} published {_at(f.latest_published_at):<22} {f.state}{nxt}"
            )
    if s.issues:
        lines += ["", "Issues"]
        for i in s.issues:
            lines += [
                f"  [{LABEL[i.severity]}] {i.title}",
                f"      {i.detail}",
                f"      -> {i.action}",
            ]
    for note in s.notes:
        lines.append(f"Note: {note}")
    return "\n".join(lines)
