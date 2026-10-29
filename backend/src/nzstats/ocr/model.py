"""Official Cash Rate decisions and the observations derived from them. Pure functions; no data access.

A decision has two dates: the day the Reserve Bank announces it and the day the new rate takes effect (usually the next
day). A rate is "in force" from its effective date. Monthly observations are derived, never stored as decisions: the
month-end rate is the rate in force on the month's last day; the monthly average weights each calendar day by the rate
in force that day, and exists only for months wholly covered by known decisions. These three can differ in a month
with a decision, so forecasts are matched to the one they state.

No OCR source is approved (docs/data-sources/ocr.md); this module is tested on synthetic decisions only.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

Decision = Literal["increase", "decrease", "unchanged"]


@dataclass(frozen=True)
class OcrDecision:
    announced_on: date
    effective_on: date
    rate: Decimal  # percent per year, the new OCR
    change_bp: (
        int | None
    )  # basis points from the previous decision; None for the first known decision
    decision: Decision
    source_url: str


def changes_bp(decisions: Sequence[OcrDecision]) -> list[tuple[OcrDecision, int | None]]:
    """Each decision with its change in basis points, computed from consecutive rates."""
    out: list[tuple[OcrDecision, int | None]] = []
    previous: Decimal | None = None
    for d in decisions:
        out.append((d, None if previous is None else int((d.rate - previous) * 100)))
        previous = d.rate
    return out


def rate_on(decisions: Sequence[OcrDecision], day: date) -> Decimal | None:
    """The OCR in force on `day`, or None before the first known effective date."""
    current = None
    for d in sorted(decisions, key=lambda d: d.effective_on):
        if d.effective_on > day:
            break
        current = d.rate
    return current


def _months(start: str, end: str) -> list[tuple[int, int]]:
    y, m = int(start[:4]), int(start[5:])
    out = []
    while (y, m) <= (int(end[:4]), int(end[5:])):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def month_end_series(decisions: Sequence[OcrDecision], start: str, end: str) -> dict[str, Decimal]:
    """The rate in force on the last day of each month `YYYY-MM` from `start` to `end`, where known."""
    out = {}
    for y, m in _months(start, end):
        rate = rate_on(decisions, date(y, m, calendar.monthrange(y, m)[1]))
        if rate is not None:
            out[f"{y:04d}-{m:02d}"] = rate
    return out


def monthly_average_series(
    decisions: Sequence[OcrDecision], start: str, end: str
) -> dict[str, Decimal]:
    """Calendar-day average of the rate in force, to three decimal places, for wholly covered months only."""
    out = {}
    for y, m in _months(start, end):
        days = calendar.monthrange(y, m)[1]
        rates = [rate_on(decisions, date(y, m, 1) + timedelta(days=k)) for k in range(days)]
        if any(r is None for r in rates):
            continue
        mean = sum(rates, Decimal(0)) / days  # type: ignore[arg-type]
        out[f"{y:04d}-{m:02d}"] = mean.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return out
