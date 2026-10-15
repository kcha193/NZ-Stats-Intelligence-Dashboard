"""Time helpers. Storage is UTC ISO-8601; display is Pacific/Auckland."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

AKL = ZoneInfo("Pacific/Auckland")
_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_akl_naive(text: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS' (as published by Stats NZ) as Auckland local time."""
    return datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=AKL)


def to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime; attach a timezone first")
    return dt.astimezone(UTC).strftime(_UTC_FMT)


def from_utc_iso(text: str) -> datetime:
    return datetime.strptime(text, _UTC_FMT).replace(tzinfo=UTC)


def to_akl_iso(value: str | datetime) -> str:
    dt = from_utc_iso(value) if isinstance(value, str) else value
    return dt.astimezone(AKL).isoformat()


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)
