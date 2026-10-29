"""The shape of a published snapshot: file names, envelopes, models and hashing. Shared by export and validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, TypeAdapter

from nzstats.models import (
    CountriesOut,
    CpiDashboardOut,
    EctDashboardOut,
    GdpDashboardOut,
    HealthOut,
    LabourDashboardOut,
    OverviewOut,
    ReleaseDetail,
    ReleaseSummary,
    RevisionsOut,
    SeriesDataOut,
)

SCHEMA_VERSION = 1
MANIFEST = "manifest.json"
ORIGIN_PRODUCTION = "production"
ORIGIN_FIXTURE = "fixture"

# Series the frontend requests by key (`useSeries`, `useRevisions`); the snapshot must carry all of them.
REQUIRED_SERIES = (
    "mig.m.net", "mig.m.arrivals", "mig.m.departures",
    "mig.ry.net", "mig.ry.arrivals", "mig.ry.departures",
    "mig.ry.net.nz", "mig.ry.net.nonnz", "mig.ry.arrivals.nz", "mig.ry.arrivals.nonnz",
    "mig.ry.departures.nz", "mig.ry.departures.nonnz",
)  # fmt: skip
REQUIRED_REVISIONS = ("mig.m.net",)
REQUIRED_FILES = (
    "overview.json", "cpi.json", "ect.json", "health.json", "releases.json", "calendar.json",
    "migration/countries.json",
)  # fmt: skip
# Dashboards written only once their category has been ingested (Phase 4C); the site shows "not yet ingested" otherwise.
OPTIONAL_DASHBOARDS = {"gdp.json": "/api/gdp", "labour-market.json": "/api/labour-market"}

# Fields that change on every export without the data changing; excluded from the content hash.
VOLATILE_KEYS = frozenset({"generated_at"})

ATTRIBUTION = {
    "source": "Stats NZ",
    "url": "https://www.stats.govt.nz/",
    "licence": "CC BY 4.0",
    "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    "note": "Independent of, and not endorsed by, Stats NZ.",
}


class CalendarMeta(BaseModel):
    """Freshness of the release calendar; the items themselves are windowed from `releases.json`."""

    last_checked_at: str | None
    last_success_at: str | None


_RELEASES = TypeAdapter(list[ReleaseSummary])


def kind_of(path: str) -> str:
    head = path.split("/", 1)[0]
    if "/" in path:
        return {
            "releases": "release",
            "series": "series",
            "revisions": "revisions",
            "migration": "countries",
        }[head]
    return path.removesuffix(".json")


# Every kind the exporter writes. Anything else in a snapshot (research data, for example) is refused.
KNOWN_KINDS = frozenset(
    "overview cpi ect gdp labour-market health calendar releases release series revisions countries".split()
)


def known_kind(path: str) -> str | None:
    """The kind of a snapshot file, or None for a path the exporter never writes."""
    try:
        kind = kind_of(path)
    except KeyError:
        return None
    return kind if kind in KNOWN_KINDS else None


def validate_payload(kind: str, payload: Any) -> Any:
    """Validate a payload against the API's own response model; returns the parsed model."""
    if kind == "releases":
        return _RELEASES.validate_python(payload)
    model = {
        "overview": OverviewOut, "cpi": CpiDashboardOut, "ect": EctDashboardOut, "gdp": GdpDashboardOut,
        "labour-market": LabourDashboardOut, "health": HealthOut,
        "calendar": CalendarMeta, "release": ReleaseDetail, "series": SeriesDataOut,
        "revisions": RevisionsOut, "countries": CountriesOut,
    }[kind]  # fmt: skip
    return model.model_validate(payload)


def dumps(obj: Any) -> str:
    """Canonical JSON: sorted keys, no NaN/Infinity, compact, UTF-8 text."""
    return (
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + "\n"
    )


def strip_volatile(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj


def content_hash(payload: Any) -> str:
    return hashlib.sha256(dumps(strip_volatile(payload)).encode("utf-8")).hexdigest()


def snapshot_id(content_hashes: dict[str, str]) -> str:
    lines = "\n".join(f"{path} {digest}" for path, digest in sorted(content_hashes.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


# `ReleaseDetail.unavailable_reason` is built by the API from the ingestion log, which includes raw error text. The
# public snapshot keeps only reasons that are fixed wording; anything else becomes the generic sentence below.
SAFE_REASON_PREFIXES = (
    "Detailed analysis is not yet available for this category",
    "Scheduled for ",
    "Delayed; now scheduled for ",
    "Stats NZ files were not available during the polling window",
    "Published, awaiting ingestion.",
    "The release was ingested, but the analysis could not be built",
)
GENERIC_REASON = "This release has not been verified here yet. The last verified data is unchanged and is shown as published."


def public_reason(reason: str | None) -> str | None:
    if reason is None or reason.startswith(SAFE_REASON_PREFIXES):
        return reason
    return GENERIC_REASON


SOURCE_HOSTS = ("stats.govt.nz", "www.stats.govt.nz")


def is_stats_nz_url(value: object) -> bool:
    """Every source link on the public site must be an https address on Stats NZ's own domain."""
    from urllib.parse import urlsplit

    if not isinstance(value, str):
        return False
    parts = urlsplit(value)
    return parts.scheme == "https" and parts.hostname in SOURCE_HOSTS and not parts.username
