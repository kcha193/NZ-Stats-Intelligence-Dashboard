"""Change calculations. Percentages are defined only for a positive base and a non-negative
current value; otherwise None ("n/a") so sign flips never produce misleading percentages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from nzstats.stats.periods import add_months


def abs_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    if previous <= 0 or current < 0:
        return None
    return (current - previous) / previous * 100.0


def pp_diff(current_pct: float | None, previous_pct: float | None) -> float | None:
    """Difference between two percentages, in percentage points."""
    return abs_change(current_pct, previous_pct)


@dataclass(frozen=True)
class Change:
    period: str
    comparison_period: str
    current: float
    previous: float
    absolute: float
    percent: float | None


def lagged_change(series: Mapping[str, float], period: str, lag_months: int) -> Change | None:
    comparison = add_months(period, -lag_months)
    if period not in series or comparison not in series:
        return None
    cur, prev = series[period], series[comparison]
    return Change(period, comparison, cur, prev, cur - prev, pct_change(cur, prev))
