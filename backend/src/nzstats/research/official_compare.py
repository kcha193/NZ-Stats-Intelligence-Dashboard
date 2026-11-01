"""Compare a figure a document reports with the official Stats NZ series, as its author could have seen it (Phase 4I).

Read-only: no request and no write. Three rules keep a comparison honest:

1. Vintage. The official value comes from the newest stored bundle published and captured on or before the
   document's date (Pacific/Auckland), never from a later revision. Missing calculation inputs in that bundle
   are not replaced by an older one. Undated bundle reactivations make later historical selection uncertain.
2. Basis. A figure is compared only with a series on the same adjustment basis. When the document does not state
   its basis, the comparison is refused for measures Stats NZ publishes on more than one basis (a monthly or
   quarterly level, or a change on the previous period). Annual changes and rolling-year totals are conventionally
   unadjusted, so they are compared with the unadjusted series.
3. Precision. The official value is rounded to the precision the document states, half away from zero (the Stats
   NZ convention), so 20,503 is reported as 20,500 when the document says 20,500.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from nzstats.research.contract import Adjustment
from nzstats.research.outcomes import akl_date
from nzstats.store.repo import get_series_row, list_vintages, vintage_points

# "annual": the series' own value, which is already an annual change (an annual average, a year-on-year rate).
Measure = Literal["level", "annual", "change_on_previous", "change_on_year"]
Status = Literal["match", "differs", "not_comparable", "no_official_value"]

_SERIES_BASIS = {
    "none": Adjustment.UNADJUSTED,
    "seasonally_adjusted": Adjustment.SEASONALLY_ADJUSTED,
    "trend": Adjustment.TREND,
}
_WORDS = {
    Adjustment.UNADJUSTED: "unadjusted",
    Adjustment.SEASONALLY_ADJUSTED: "seasonally adjusted",
    Adjustment.TREND: "trend",
}
_MONTHS_BACK = {"monthly": 1, "quarterly": 3, "rolling_annual": 1}


@dataclass(frozen=True)
class Comparison:
    status: Status
    reason: str
    official: float | None = None  # rounded to the document's precision
    release_key: str | None = None
    released_on: str | None = None  # Pacific/Auckland date of that release


def _months_back(period: str, n: int) -> str:
    index = int(period[:4]) * 12 + int(period[5:7]) - 1 - n
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _basis_refusal(
    adjustment: Adjustment, series_basis: Adjustment, frequency: str, measure: Measure
) -> str | None:
    if adjustment is Adjustment.NOT_STATED:
        if measure in ("annual", "change_on_year") or frequency == "rolling_annual":
            return None if series_basis is Adjustment.UNADJUSTED else (
                f"the document does not state its adjustment basis, and an annual change is conventionally"
                f" unadjusted, but this series is {_WORDS[series_basis]}"
            )  # fmt: skip
        return (
            "the document does not state the adjustment basis of this figure, and Stats NZ publishes the"
            " measure on more than one basis (seasonally adjusted and unadjusted): do not compare it"
        )
    if adjustment is not series_basis:
        return f"the document's figure is {_WORDS[adjustment]}, but the series is {_WORDS[series_basis]}"
    return None


def _value(
    points: dict[str, float], period: str, measure: Measure, frequency: str
) -> Decimal | None:
    if period not in points:
        return None
    now = Decimal(repr(points[period]))
    if measure in ("level", "annual"):
        return now
    back = 12 if measure == "change_on_year" else _MONTHS_BACK[frequency]
    before = points.get(_months_back(period, back))
    if before is None or before == 0:
        return None
    return (now / Decimal(repr(before)) - 1) * 100


def _round_like(value: Decimal, document_value: float | int | str | Decimal) -> float:
    """`value` at the precision of `document_value`: its decimal places, or its trailing zeros if a whole number."""
    stated = Decimal(str(document_value).replace(",", ""))
    if "." not in str(document_value):
        stated = stated.normalize()  # whole numbers use their trailing zeros as the precision
    exponent = stated.as_tuple().exponent
    assert isinstance(exponent, int)
    step = Decimal(1).scaleb(exponent)
    return float((value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step)


def _activation_uncertain(conn: sqlite3.Connection, vintage_id: int, published_on: date) -> bool:
    rows = conn.execute(
        "SELECT id, activation, captured_at, bundle_sha256 FROM vintage WHERE release_id ="
        " (SELECT release_id FROM vintage WHERE id = ?)",
        (vintage_id,),
    ).fetchall()
    visible_bundles = {
        row["bundle_sha256"]
        for row in rows
        if akl_date(row["captured_at"]) <= published_on.isoformat()
    }
    # Migration 002 starts activation at id; create_vintage advances both counters together until
    # a reactivation advances only activation. No activation timestamps survive. A counter offset
    # can also follow an unrelated release's reactivation, so refusal is deliberately conservative.
    # Before the second bundle's capture, there is still only one eligible historical value.
    return len(visible_bundles) > 1 and any(row["activation"] != row["id"] for row in rows)


def compare_figure(
    conn: sqlite3.Connection,
    *,
    series: str,
    period: str,
    measure: Measure,
    document_value: float | int | str | Decimal,
    adjustment: Adjustment,
    published_on: date,
) -> Comparison:
    """Compare a figure with a vintage.

    Pass original number text (or Decimal) to preserve its written decimal places; floats cannot preserve
    trailing fractional zeros. A whole number's trailing zeros indicate rounding to tens, hundreds, etc.
    """
    if conn.execute("SELECT 1 FROM series WHERE key = ?", (series,)).fetchone() is None:
        return Comparison("no_official_value", f"no stored series {series}")
    visible = [
        v
        for v in list_vintages(conn, series)
        if akl_date(v.published_at) <= published_on.isoformat()
        and akl_date(v.captured_at) <= published_on.isoformat()
    ]
    for info in sorted(
        visible, key=lambda v: (v.published_at, v.captured_at, v.vintage_id), reverse=True
    ):
        points = {p: pt.value for p, pt in vintage_points(conn, info.vintage_id).items()}
        if period not in points:
            continue
        if _activation_uncertain(conn, info.vintage_id, published_on):
            return Comparison(
                "not_comparable",
                "the release's bundle activation history has no dates; its historical value is uncertain",
            )
        meta = get_series_row(conn, series, info.vintage_id)
        if meta is None:
            return Comparison(
                "not_comparable", "the selected vintage has no stored series definition"
            )
        frequency, basis = meta["frequency"], _SERIES_BASIS.get(meta["seasonal_adjustment"])
        if basis is None:
            return Comparison(
                "not_comparable",
                f"the series' adjustment basis {meta['seasonal_adjustment']!r} is not known",
            )
        refusal = _basis_refusal(adjustment, basis, frequency, measure)
        if refusal is not None:
            return Comparison("not_comparable", refusal)
        value = _value(points, period, measure, frequency)
        if value is None:
            return Comparison(
                "no_official_value",
                f"the selected vintage ({info.release_key}) lacks usable inputs for {measure} of"
                f" {series} for {period}",
            )
        official = _round_like(value, document_value)
        status: Status = (
            "match"
            if Decimal(str(official)) == Decimal(str(document_value).replace(",", ""))
            else "differs"
        )
        released = akl_date(info.published_at)
        return Comparison(status, f"as published on {released} ({info.release_key})", official,
                          info.release_key, released)  # fmt: skip
    return Comparison(
        "no_official_value",
        f"no stored release published by {published_on.isoformat()} holds {series} for {period}",
    )
