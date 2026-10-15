from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from nzstats.domain import Observation, Point, SeriesDef
from nzstats.sources.release_page import ReleasePage


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str  # "error" blocks ingestion; "warning" is recorded only
    message: str


@dataclass(frozen=True)
class ParsedSeries:
    definition: SeriesDef
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class ParsedBundle:
    layout_version: str
    series: tuple[ParsedSeries, ...]


class Adapter(Protocol):
    series_slug: str
    required_downloads: tuple[str, ...]
    previous_keys: tuple[str, ...]  # series whose previous vintage is loaded for validation

    def parse(self, page: ReleasePage, files: Mapping[str, bytes]) -> ParsedBundle: ...

    def validate(
        self,
        bundle: ParsedBundle,
        *,
        reference_period: str | None,
        previous: Mapping[str, Mapping[str, Point]],
    ) -> list[Finding]: ...
