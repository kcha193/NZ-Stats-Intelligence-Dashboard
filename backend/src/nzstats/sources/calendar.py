"""Stats NZ release calendar: ICS export (upcoming) and month endpoint (published + upcoming)."""

from __future__ import annotations

import calendar as _calendar
import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from nzstats.clock import AKL, parse_akl_naive
from nzstats.domain import ErrorClass, IngestError, ReleaseRef, ReleaseStatus
from nzstats.slug import slugify
from nzstats.sources.fetcher import Fetcher

log = logging.getLogger(__name__)

_MONTHS = {name.lower(): i for i, name in enumerate(_calendar.month_name) if name}
_MONTH_YEAR = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)


@dataclass(frozen=True)
class TitleParts:
    series_slug: str
    period_label: str | None
    reference_period: str | None


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    summary: str
    start: datetime


def parse_title(title: str) -> TitleParts:
    name, sep, label = title.partition(": ")
    if not sep:
        return TitleParts(slugify(title), None, None)
    label = label.strip()
    match = _MONTH_YEAR.search(label)
    period = f"{int(match.group(2)):04d}-{_MONTHS[match.group(1).lower()]:02d}" if match else None
    return TitleParts(slugify(name), label, period)


def make_release_key(title: str) -> str:
    parts = parse_title(" ".join(title.split()))
    return f"{parts.series_slug}:{(parts.period_label or '').lower()}"


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _parse_dtstart(params: str, value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).astimezone(AKL)
    if "VALUE=DATE" in params:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=AKL)
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=AKL)


def parse_ics(text: str) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    current: dict[str, object] | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            if {"uid", "summary", "start"} <= current.keys():
                events.append(CalendarEvent(current["uid"], current["summary"], current["start"]))
            else:
                log.warning("skipping incomplete VEVENT: %s", sorted(current))
            current = None
        elif current is not None and ":" in line:
            head, _, value = line.partition(":")
            name, _, params = head.partition(";")
            if name == "UID":
                current["uid"] = value.strip()
            elif name == "SUMMARY":
                current["summary"] = _unescape(value).strip()
            elif name == "DTSTART":
                try:
                    current["start"] = _parse_dtstart(params, value)
                except ValueError:
                    log.warning("unparseable DTSTART %r", line)
    return events


def _ref(title: str, published_at: datetime, status: ReleaseStatus, **kw) -> ReleaseRef:
    parts = parse_title(" ".join(title.split()))
    return ReleaseRef(
        release_key=make_release_key(title),
        series_slug=parts.series_slug,
        title=title.strip(),
        period_label=parts.period_label,
        reference_period=parts.reference_period,
        published_at=published_at,
        status=status,
        **kw,
    )


def events_to_refs(events: Iterable[CalendarEvent]) -> list[ReleaseRef]:
    return [
        _ref(e.summary, e.start, ReleaseStatus.SCHEDULED, statsnz_id=e.uid.split("@")[0])
        for e in events
    ]


def parse_release_month(payload: Mapping, base_url: str) -> list[ReleaseRef]:
    items = payload.get("items") if isinstance(payload, Mapping) else None
    if not isinstance(items, Mapping) or not {"published", "upcoming"} & items.keys():
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "release month payload has no 'items'")
    refs: list[ReleaseRef] = []
    try:
        for p in items.get("published", []):
            term = p["DateTaxonomyTerm"]
            refs.append(
                _ref(
                    term["DisplayName"],
                    parse_akl_naive(term["PublicationDate"]),
                    ReleaseStatus.PUBLISHED,
                    page_url=base_url + p["PageLink"],
                    headline=(p.get("MetaDescription") or "").strip() or None,
                    statsnz_id=str(p.get("ID") or ""),
                )
            )
        for u in items.get("upcoming", []):
            refs.append(
                _ref(
                    u["DisplayName"],
                    parse_akl_naive(u["PublicationDate"]),
                    ReleaseStatus.SCHEDULED,
                )
            )
    except (KeyError, TypeError, ValueError) as exc:
        raise IngestError(
            ErrorClass.LAYOUT_CHANGED, f"release month entry malformed: {exc!r}"
        ) from exc
    return refs


def fetch_calendar(fetcher: Fetcher, base_url: str, ics_path: str) -> list[ReleaseRef]:
    result = fetcher.get(base_url + ics_path, expect=("text/calendar",))
    refs = events_to_refs(parse_ics(result.body.decode("utf-8")))
    if not refs:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "calendar export contained no events")
    return refs


def fetch_release_month(
    fetcher: Fetcher, base_url: str, path_template: str, month: str
) -> list[ReleaseRef]:
    result = fetcher.get(base_url + path_template.format(month=month), expect=("application/json",))
    try:
        payload = json.loads(result.body)
    except json.JSONDecodeError as exc:
        raise IngestError(ErrorClass.LAYOUT_CHANGED, "release month is not JSON") from exc
    return parse_release_month(payload, base_url)
