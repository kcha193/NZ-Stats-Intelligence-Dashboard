from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PercentileContext:
    rank: int  # 1 = highest in history
    n: int
    percentile: float  # share of observations <= value, 0-100


def percentile_context(value: float, history: Sequence[float]) -> PercentileContext | None:
    """`history` must include `value` itself. Rarity is not economic significance."""
    n = len(history)
    if n < 2:
        return None
    higher = sum(1 for v in history if v > value)
    at_or_below = sum(1 for v in history if v <= value)
    return PercentileContext(rank=higher + 1, n=n, percentile=100.0 * at_or_below / n)
