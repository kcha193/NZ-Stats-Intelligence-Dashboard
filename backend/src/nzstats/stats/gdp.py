"""Quarterly GDP arithmetic. Pure functions over `{YYYY-MM quarter-end: level}` mappings.

Quarterly and annual changes of a quarter use `stats.cpi.quarterly_changes` and `annual_changes`; this module adds the
annual average change, which Stats NZ's release page calls "Annual growth".
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

from nzstats.stats.cpi import is_quarter_end
from nzstats.stats.periods import add_months


def annual_average_changes(levels: Mapping[str, float]) -> dict[str, float]:
    """Percent change of the four quarters ending at each quarter against the four quarters before them.

    Only where all eight quarters are present; never a partial year.
    """
    for period, level in levels.items():
        if not is_quarter_end(period):
            raise ValueError(f"not a quarter-end period: {period!r}")
        if not math.isfinite(level) or level <= 0:
            raise ValueError(f"level must be positive and finite: {period} {level!r}")
    out = {}
    for period in levels:
        quarters = [add_months(period, -3 * k) for k in range(8)]
        if all(q in levels for q in quarters):
            recent = sum(levels[q] for q in quarters[:4])
            earlier = sum(levels[q] for q in quarters[4:])
            out[period] = (recent / earlier - 1) * 100
    return out


def round_1dp(value: float) -> float:
    """Round to one decimal place, half away from zero, as Stats NZ publishes percentages."""
    return float(Decimal(repr(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
