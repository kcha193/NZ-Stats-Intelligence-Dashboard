"""Publication dates as institutions state them, parsed conservatively.

A date-only value is a civil date in New Zealand (precision `day`, or `month` for "August 2026"); no
time of day is invented. An instant is kept in UTC, and its New Zealand civil date is derived with the
real time-zone rules, so daylight saving is handled. A publication date is not a data reference period
and nothing here derives one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from nzstats.clock import AKL

EARLIEST = date(2000, 1, 1)
MAX_TEXT = 64
_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
            ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}  # fmt: skip
_WEEKDAY = r"(?:(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*,?\s+)?"
_DAY_MONTH_YEAR = re.compile(
    rf"^{_WEEKDAY}(\d{{1,2}})(?:st|nd|rd|th)?\s+([a-z]+)\.?,?\s+(\d{{4}})$", re.IGNORECASE
)
_MONTH_DAY_YEAR = re.compile(
    rf"^{_WEEKDAY}([a-z]+)\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})$", re.IGNORECASE
)
_MONTH_YEAR = re.compile(r"^([a-z]+)\.?\s+(\d{4})$", re.IGNORECASE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_INSTANT = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$"
)

Precision = Literal["instant", "day", "month"]


class DateParseError(ValueError):
    """Fixed wording; never contains the input text."""


@dataclass(frozen=True)
class PublishedDate:
    on: date  # civil date in New Zealand
    at: datetime | None  # UTC instant, only when the source states a time
    precision: Precision


def parse_published(text: str, *, now: datetime) -> PublishedDate:
    value = (text or "").strip()
    if not value or len(value) > MAX_TEXT:
        raise DateParseError("unrecognised publication date")
    if _ISO_INSTANT.match(value):
        try:
            stamp = datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError:
            raise DateParseError("invalid publication date") from None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=AKL)
        at = stamp.astimezone(UTC)
        return _checked(PublishedDate(at.astimezone(AKL).date(), at, "instant"), now)
    if _ISO_DATE.match(value):
        return _checked(PublishedDate(_make(*map(int, value.split("-"))), None, "day"), now)
    if m := _DAY_MONTH_YEAR.match(value):
        day, month, year = m.groups()
        return _checked(PublishedDate(_make(int(year), _month(month), int(day)), None, "day"), now)
    if m := _MONTH_DAY_YEAR.match(value):
        month, day, year = m.groups()
        return _checked(PublishedDate(_make(int(year), _month(month), int(day)), None, "day"), now)
    if m := _MONTH_YEAR.match(value):
        month, year = m.groups()
        return _checked(PublishedDate(_make(int(year), _month(month), 1), None, "month"), now)
    raise DateParseError("unrecognised publication date")


def date_from_url(url: str, regex: str, fmt: str, *, now: datetime) -> PublishedDate | None:
    """A day-precision date from a file name, e.g. `ANZ-QEO-20260813.pdf` with `%Y%m%d`."""
    m = re.search(regex, url)
    if m is None:
        return None
    try:
        day = datetime.strptime(m.group(1), fmt).date()
    except ValueError:
        raise DateParseError("invalid date in url") from None
    return _checked(PublishedDate(day, None, "day"), now)


def _month(name: str) -> int:
    try:
        return _MONTHS[name.lower()]
    except KeyError:
        raise DateParseError("unrecognised month") from None


def _make(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise DateParseError("invalid publication date") from None


def _checked(value: PublishedDate, now: datetime) -> PublishedDate:
    today = now.astimezone(AKL).date()
    if value.on < EARLIEST or value.on > today + timedelta(days=1):
        raise DateParseError("publication date out of range")
    return value
