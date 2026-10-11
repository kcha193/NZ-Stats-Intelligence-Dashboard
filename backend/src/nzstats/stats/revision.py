from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nzstats.domain import ObsStatus, Point
from nzstats.stats.changes import pct_change


@dataclass(frozen=True)
class Revision:
    period: str
    original: float
    revised: float
    absolute: float
    percent: float | None
    original_status: ObsStatus
    revised_status: ObsStatus


@dataclass(frozen=True)
class RevisionSummary:
    n_common: int
    n_revised: int
    max_abs: Revision | None
    mean_abs: float | None  # mean |revision| over revised periods only


def revisions(original: Mapping[str, Point], revised: Mapping[str, Point]) -> list[Revision]:
    """Revisions for periods present in both vintages, oldest period first."""
    out = []
    for period in sorted(set(original) & set(revised)):
        o, r = original[period], revised[period]
        out.append(
            Revision(
                period=period,
                original=o.value,
                revised=r.value,
                absolute=r.value - o.value,
                percent=pct_change(r.value, o.value),
                original_status=o.status,
                revised_status=r.status,
            )
        )
    return out


def summarise(revs: Sequence[Revision]) -> RevisionSummary:
    changed = [r for r in revs if r.absolute != 0]
    if not changed:
        return RevisionSummary(len(revs), 0, None, None)
    biggest = max(changed, key=lambda r: abs(r.absolute))
    mean_abs = sum(abs(r.absolute) for r in changed) / len(changed)
    return RevisionSummary(len(revs), len(changed), biggest, mean_abs)
