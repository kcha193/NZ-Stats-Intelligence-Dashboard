from __future__ import annotations

from nzstats.domain import SeriesDef


class IncompatibleSeries(ValueError):
    """Raised when two series must not be compared or charted together."""


def check_compatible(a: SeriesDef, b: SeriesDef) -> None:
    if a.frequency != b.frequency:
        raise IncompatibleSeries(f"frequency differs: {a.frequency} vs {b.frequency}")
    if a.unit != b.unit:
        raise IncompatibleSeries(f"unit differs: {a.unit} vs {b.unit}")
    if a.adjustment != b.adjustment:
        raise IncompatibleSeries(f"adjustment differs: {a.adjustment} vs {b.adjustment}")
    if a.definition_id != b.definition_id:
        raise IncompatibleSeries(f"definition differs: {a.definition_id} vs {b.definition_id}")


def compatible(a: SeriesDef, b: SeriesDef) -> bool:
    try:
        check_compatible(a, b)
    except IncompatibleSeries:
        return False
    return True
