"""Table-derived figures against verified model claims (Phase 4AF). Pure and read-only.

Two independent readings of one document are compared, per document version, on the identity the bank analytics
already use (indicator, seasonal adjustment, the statistical basis the label states, the horizon). The result is a
fixed class per matched group, never a verdict on whether either reading is *economically right*: two methods that
agree can share a misreading of the same page, so agreement is recorded as agreement and nothing else.

Problems with *what is being compared* are decided before the numbers are:

    ambiguous_or_unsupported  several differing readings of one identity, or a measure that cannot be read
    attribution_mismatch      the table attributes the figure to someone other than the bank
    units_mismatch            the same identity, different units
    horizon_mismatch          one leftover table figure and one leftover claim of one measure, different horizons
    no_counterpart            nothing on the other side states this identity

then the values: exact_match, rounding_difference (the more precise value, rounded half-up to the other's printed
precision, equals it) and contradictory_value. A table row that was rejected during interpretation has no identity
and cannot be matched; the rejection codes are reported separately by `table_store.load_rejections`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from nzstats.research.bank_forecast import (
    NormalizedForecast,
    canonical_label,
    derive_adjustment,
)
from nzstats.research.compare import basis_of, horizon_of
from nzstats.research.table_context import evidence_texts, stored_context_rejection
from nzstats.research.table_store import StoredTableForecast

Class = Literal[
    "exact_match", "rounding_difference", "units_mismatch", "horizon_mismatch",
    "attribution_mismatch", "contradictory_value", "ambiguous_or_unsupported", "no_counterpart",
]  # fmt: skip
CLASSES: tuple[Class, ...] = (
    "exact_match", "rounding_difference", "units_mismatch", "horizon_mismatch",
    "attribution_mismatch", "contradictory_value", "ambiguous_or_unsupported", "no_counterpart",
)  # fmt: skip


@dataclass(frozen=True)
class Reconciliation:
    version_id: int
    table_ids: tuple[int, ...]
    claim_paths: tuple[str, ...]
    cls: Class
    note_code: str


@dataclass(frozen=True)
class _Item:
    key: tuple | None  # (indicator, adjustment, basis, horizon key); None when it cannot be read
    family: tuple | None  # the same without the horizon
    value: Decimal
    unit: str
    third_party: bool
    ref: int | str


def _identity(
    indicator: str, label: str, horizon: str, adjustment: str
) -> tuple[tuple | None, tuple | None]:
    basis = basis_of(
        indicator, label, horizon, "percent"
    )  # units are compared later, not part of identity
    hk = horizon_of(horizon)
    if basis is None or hk is None:
        return None, None
    return (indicator, adjustment, basis, hk[0]), (indicator, adjustment, basis)


def _table_item(t: StoredTableForecast) -> _Item:
    texts = evidence_texts(t.evidence)
    context = " ".join((t.evidence.get("document_title") or "", *texts))
    adjustment = derive_adjustment(t.label, context)
    key, family = _identity(
        t.indicator, canonical_label(t.label, adjustment), t.horizon, adjustment
    )
    if stored_context_rejection(t.label, t.evidence):
        key, family = None, None
    assert t.value is not None
    return _Item(key, family, t.value, t.unit, t.author_role == "third_party", t.id)


def _claim_item(c: NormalizedForecast) -> _Item:
    f = c.forecast
    key, family = _identity(f.indicator, f.indicator_label, f.horizon, c.adjustment)
    assert f.value is not None
    return _Item(key, family, Decimal(str(f.value)), f.unit or "", False, c.claim_path)


def _decimals(d: Decimal) -> int:
    return max(0, -int(d.as_tuple().exponent))


def _rounds_to(precise: Decimal, coarse: Decimal) -> bool:
    return precise.quantize(Decimal(1).scaleb(-_decimals(coarse)), rounding=ROUND_HALF_UP) == coarse


def _compare(t: _Item, c: _Item) -> tuple[Class, str]:
    if t.third_party:
        return "attribution_mismatch", "table_attributes_to_another_source"
    if t.unit != c.unit:
        return "units_mismatch", "units_differ"
    if t.value == c.value:
        return "exact_match", "values_equal"
    dt, dc = _decimals(t.value), _decimals(c.value)
    if (dt > dc and _rounds_to(t.value, c.value)) or (dc > dt and _rounds_to(c.value, t.value)):
        return "rounding_difference", "rounds_to_the_other_precision"
    return "contradictory_value", "values_differ"


def reconcile(
    table: Sequence[StoredTableForecast], claims: Sequence[NormalizedForecast]
) -> list[Reconciliation]:
    """One entry per matched group or lone item, per document version. Actuals and missing figures are not reconciled."""
    tables: dict[int, list[_Item]] = defaultdict(list)
    for t in table:
        if t.kind == "forecast" and not t.missing and t.value is not None:
            tables[t.version_id].append(_table_item(t))
    cl: dict[int, list[_Item]] = defaultdict(list)
    for c in claims:
        # A scenario is not the central forecast the table states; it is neither matched nor contradicted by it.
        if c.forecast.value is not None and not c.forecast.scenario:
            cl[c.document_version_id].append(_claim_item(c))
    out: list[Reconciliation] = []
    for version in sorted(set(tables) | set(cl)):
        out.extend(_version(version, tables.get(version, []), cl.get(version, [])))
    return out


def _version(version: int, tabs: list[_Item], cls_: list[_Item]) -> list[Reconciliation]:
    out: list[Reconciliation] = []

    def add(ts: list[_Item], cs: list[_Item], cls: Class, note: str) -> None:
        out.append(Reconciliation(version, tuple(sorted(int(i.ref) for i in ts)), tuple(sorted(str(i.ref) for i in cs)), cls, note))  # fmt: skip

    groups: dict[tuple, tuple[list[_Item], list[_Item]]] = defaultdict(lambda: ([], []))
    for item in tabs:
        if item.key is None:
            add([item], [], "ambiguous_or_unsupported", "measure_unreadable")
        else:
            groups[item.key][0].append(item)
    for item in cls_:
        if item.key is None:
            add([], [item], "ambiguous_or_unsupported", "measure_unreadable")
        else:
            groups[item.key][1].append(item)
    left_t: dict[tuple, list[_Item]] = defaultdict(list)
    left_c: dict[tuple, list[_Item]] = defaultdict(list)
    for key in sorted(groups, key=str):
        ts, cs = groups[key]
        if ts and cs:
            if (
                len({(i.value, i.unit, i.third_party) for i in ts}) > 1
                or len({(i.value, i.unit) for i in cs}) > 1
            ):
                add(ts, cs, "ambiguous_or_unsupported", "several_differing_readings")
            else:
                cls, note = _compare(ts[0], cs[0])
                add(ts, cs, cls, note)
        elif ts:
            left_t[ts[0].family].extend(ts)
        else:
            left_c[cs[0].family].extend(cs)
    for family in sorted(set(left_t) | set(left_c), key=str):
        ts, cs = left_t.get(family, []), left_c.get(family, [])
        if len(ts) == 1 and len(cs) == 1:
            add(ts, cs, "horizon_mismatch", "horizon_differs")
        else:
            for i in ts:
                add([i], [], "no_counterpart", "only_in_the_table")
            for i in cs:
                add([], [i], "no_counterpart", "only_in_the_claims")
    return sorted(out, key=lambda r: (r.table_ids or (10**12,), r.claim_paths))


def summary_counts(rs: Sequence[Reconciliation]) -> dict[str, int]:
    counts = {c: n for c in CLASSES if (n := sum(r.cls == c for r in rs))}
    return counts
