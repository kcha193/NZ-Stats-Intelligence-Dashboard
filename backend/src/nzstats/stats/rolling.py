from __future__ import annotations

from collections.abc import Mapping

from nzstats.stats.periods import add_months


def rolling_by_period(
    series: Mapping[str, float], window: int, *, mean: bool = False
) -> dict[str, float]:
    """Rolling sum (or mean) ending at each period; windows containing a missing month are skipped."""
    out: dict[str, float] = {}
    for period in sorted(series):
        months = [add_months(period, -i) for i in range(window)]
        if all(m in series for m in months):
            total = sum(series[m] for m in months)
            out[period] = total / window if mean else total
    return out
