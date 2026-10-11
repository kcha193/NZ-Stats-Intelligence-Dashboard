"""Shared domain types. No I/O here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Frequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ROLLING_ANNUAL = "rolling_annual"


class Adjustment(StrEnum):
    NONE = "none"
    SEASONALLY_ADJUSTED = "seasonally_adjusted"
    TREND = "trend"


class ObsStatus(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"
    UNKNOWN = "unknown"


class ReleaseStatus(StrEnum):
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    DELAYED = "delayed"
    CORRECTED = "corrected"
    UNAVAILABLE = "unavailable"


class ErrorClass(StrEnum):
    NETWORK = "network"
    BLOCKED = "blocked"
    NOT_FOUND = "not_found"
    LAYOUT_CHANGED = "layout_changed"
    VALIDATION_FAILED = "validation_failed"
    UNEXPECTED = "unexpected"


class IngestError(Exception):
    def __init__(self, error_class: ErrorClass, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.url = url


@dataclass(frozen=True)
class SeriesDef:
    key: str
    name: str
    unit: str
    frequency: Frequency
    adjustment: Adjustment
    definition: str
    definition_id: str  # series sharing a definition_id measure the same concept
    category: str  # e.g. "migration", "migration:country", "migration:region"
    source_url: str | None = None


@dataclass(frozen=True)
class Observation:
    series_key: str
    period: str  # 'YYYY-MM'; for ROLLING_ANNUAL this is the year-ended month
    value: float
    status: ObsStatus
    std_error: float | None = None
    released_in: str | None = None  # 'YYYY-MM' of the release that last published this value


@dataclass(frozen=True)
class Point:
    period: str
    value: float
    status: ObsStatus


@dataclass(frozen=True)
class ReleaseRef:
    release_key: str
    series_slug: str
    title: str
    period_label: str | None
    reference_period: str | None  # 'YYYY-MM' when derivable
    published_at: datetime  # timezone-aware
    status: ReleaseStatus
    page_url: str | None = None
    headline: str | None = None
    statsnz_id: str | None = None
