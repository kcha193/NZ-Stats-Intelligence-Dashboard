"""Quarterly CPI arithmetic. Pure functions over `{YYYY-MM quarter-end: index level}` mappings."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

from nzstats.stats.periods import add_months, parse_month

QUARTER_MONTHS = ("03", "06", "09", "12")


def is_quarter_end(period: str) -> bool:
    return period[5:] in QUARTER_MONTHS and parse_month(period) is not None


def _checked(levels: Mapping[str, float]) -> None:
    for period, level in levels.items():
        if not is_quarter_end(period):
            raise ValueError(f"not a quarter-end period: {period!r}")
        if not math.isfinite(level) or level <= 0:
            raise ValueError(f"index level must be positive and finite: {period} {level!r}")


def _changes(levels: Mapping[str, float], lag_months: int) -> dict[str, float]:
    _checked(levels)
    out = {}
    for period, level in levels.items():
        earlier = levels.get(add_months(period, -lag_months))
        if earlier is not None:
            out[period] = (level / earlier - 1) * 100
    return out


def quarterly_changes(levels: Mapping[str, float]) -> dict[str, float]:
    """Percent change from the preceding quarter, only where that quarter is present."""
    return _changes(levels, 3)


def annual_changes(levels: Mapping[str, float]) -> dict[str, float]:
    """Percent change from the same quarter one year earlier, only where it is present."""
    return _changes(levels, 12)


def contiguous_run(periods: Iterable[str]) -> list[str]:
    """The latest unbroken run of consecutive quarters, oldest first."""
    ordered = sorted(set(periods))
    start = len(ordered) - 1
    while start > 0 and add_months(ordered[start - 1], 3) == ordered[start]:
        start -= 1
    return ordered[start:]
