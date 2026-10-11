"""Validation rules. Temporary stub; Task 8 replaces it with the real rules."""

from __future__ import annotations

from collections.abc import Mapping

from nzstats.adapters.base import Finding, ParsedBundle
from nzstats.domain import Point


def validate_migration(
    bundle: ParsedBundle,
    *,
    reference_period: str | None,
    previous: Mapping[str, Mapping[str, Point]],
) -> list[Finding]:
    return []
